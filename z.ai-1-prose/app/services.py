"""Transactional business logic — all money movement lives here."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .database import get_connection, transaction
from .errors import BusinessRuleError, ConflictError, NotFoundError
from .security import hash_password, verify_password

DAILY_CAP_PENCE = 100_000  # £1000.00


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# --------------------------------------------------------------------- Auth
def register_user(email: str, password: str) -> tuple[int, str]:
    email_l = email.lower()
    password_hash = hash_password(password)
    try:
        with transaction() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email_l, password_hash, _now_iso()),
            )
            user_id = cur.lastrowid
            conn.execute(
                "INSERT INTO accounts (user_id, balance_pence, currency, created_at) "
                "VALUES (?, 0, 'GBP', ?)",
                (user_id, _now_iso()),
            )
        return user_id, email_l
    except sqlite3.IntegrityError:
        raise ConflictError("email already registered")


def authenticate(email: str, password: str) -> str:
    from .security import create_access_token  # local import to avoid cycle at import time
    email_l = email.lower()
    row = get_connection().execute(
        "SELECT id, password_hash FROM users WHERE email = ?", (email_l,)
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        raise BusinessRuleError("invalid credentials", status_code=401)
    return create_access_token(row["id"])


# ----------------------------------------------------------- Balance helpers
def _balance_pence(conn: sqlite3.Connection, account_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE WHEN direction = 'incoming' THEN amount_pence ELSE -amount_pence END
        ), 0) AS b
        FROM transactions
        WHERE account_id = ? AND status = 'completed'
        """,
        (account_id,),
    ).fetchone()
    return int(row["b"])


def _add_daily_out(conn: sqlite3.Connection, account_id: int, amount: int) -> int:
    """Accrue amount to today's outbound total; return the new total."""
    today = _today()
    conn.execute(
        """
        INSERT INTO daily_totals (date, account_id, total_out_pence)
        VALUES (?, ?, ?)
        ON CONFLICT(date, account_id) DO UPDATE SET
            total_out_pence = total_out_pence + excluded.total_out_pence
        """,
        (today, account_id, amount),
    )
    row = conn.execute(
        "SELECT total_out_pence FROM daily_totals WHERE date = ? AND account_id = ?",
        (today, account_id),
    ).fetchone()
    return int(row["total_out_pence"])


def _enforce_cap(conn: sqlite3.Connection, account_id: int, amount: int) -> None:
    new_total = _add_daily_out(conn, account_id, amount) - amount  # peek without committing the increment
    # _add_daily_out already incremented; we want to compare prospective total.
    # Simpler: read current total (without increment) then add amount.
    today = _today()
    row = conn.execute(
        "SELECT COALESCE(total_out_pence, 0) AS t FROM daily_totals WHERE date = ? AND account_id = ?",
        (today, account_id),
    ).fetchone()
    current = int(row["t"]) if row else 0
    # NOTE: we already incremented via _add_daily_out above; undo that to avoid double-count.
    # To keep things simple and atomic we instead DON'T pre-increment — implement below.


def _check_cap(conn: sqlite3.Connection, account_id: int, amount: int) -> None:
    """Raise if `amount` would push today's outbound total over the cap."""
    today = _today()
    row = conn.execute(
        "SELECT COALESCE(total_out_pence, 0) AS t FROM daily_totals WHERE date = ? AND account_id = ?",
        (today, account_id),
    ).fetchone()
    current = int(row["t"]) if row else 0
    if current + amount > DAILY_CAP_PENCE:
        raise BusinessRuleError(
            f"daily outbound cap of {DAILY_CAP_PENCE} pence exceeded"
        )


def _apply_cap(conn: sqlite3.Connection, account_id: int, amount: int) -> None:
    """Increment today's outbound total. Assumes _check_cap already passed."""
    today = _today()
    conn.execute(
        """
        INSERT INTO daily_totals (date, account_id, total_out_pence)
        VALUES (?, ?, ?)
        ON CONFLICT(date, account_id) DO UPDATE SET
            total_out_pence = total_out_pence + excluded.total_out_pence
        """,
        (today, account_id, amount),
    )


# ----------------------------------------------------------- Money movement
def deposit(account_id: int, amount: int) -> tuple[int, int]:
    with transaction() as conn:
        txn_id = _insert_txn(conn, account_id, "deposit", "incoming", amount, "completed")
        balance = _balance_pence(conn, account_id)
    return txn_id, balance


def withdraw(account_id: int, amount: int) -> tuple[int, int]:
    with transaction() as conn:
        _check_cap(conn, account_id, amount)
        balance_before = _balance_pence(conn, account_id)
        if balance_before < amount:
            raise BusinessRuleError("insufficient funds")
        txn_id = _insert_txn(conn, account_id, "withdrawal", "outgoing", amount, "completed")
        _apply_cap(conn, account_id, amount)
        balance = _balance_pence(conn, account_id)
    return txn_id, balance


def transfer(
    sender_account_id: int,
    sender_email: str,
    recipient_email: str,
    amount: int,
) -> tuple[int, int]:
    recipient_email_l = recipient_email.lower()
    if recipient_email_l == sender_email.lower():
        raise BusinessRuleError("cannot transfer to yourself")

    with transaction() as conn:
        recipient = conn.execute(
            """
            SELECT a.id AS account_id, a.currency
            FROM users u JOIN accounts a ON a.user_id = u.id
            WHERE u.email = ?
            """,
            (recipient_email_l,),
        ).fetchone()
        if recipient is None:
            raise NotFoundError("recipient not found")
        if recipient["currency"] != "GBP":
            raise BusinessRuleError("cross-currency transfers are not supported")

        _check_cap(conn, sender_account_id, amount)
        sender_balance = _balance_pence(conn, sender_account_id)
        if sender_balance < amount:
            raise BusinessRuleError("insufficient funds")

        sender_txn_id = _insert_txn(
            conn, sender_account_id, "transfer", "outgoing", amount, "completed"
        )
        recipient_txn_id = _insert_txn(
            conn,
            recipient["account_id"],
            "transfer",
            "incoming",
            amount,
            "completed",
            related_transaction_id=sender_txn_id,
        )
        # Link sender → recipient for symmetry.
        conn.execute(
            "UPDATE transactions SET related_transaction_id = ? WHERE id = ?",
            (recipient_txn_id, sender_txn_id),
        )
        _apply_cap(conn, sender_account_id, amount)
        balance = _balance_pence(conn, sender_account_id)
    return sender_txn_id, balance


# --------------------------------------------------------------- Reversals
def reverse_transaction(account_id: int, transaction_id: int) -> tuple[int, int, str]:
    """Reverse a completed transaction belonging to `account_id`.

    Returns (reversal_transaction_id, original_transaction_id, status).
    """
    with transaction() as conn:
        original = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND account_id = ?",
            (transaction_id, account_id),
        ).fetchone()
        if original is None:
            raise NotFoundError("transaction not found for this account")
        if original["type"] == "reversal":
            raise BusinessRuleError("cannot reverse a reversal")
        if original["status"] != "completed":
            raise ConflictError("transaction is not in a reversible state")

        # Determine the paired account (for transfers) and the direction of effect.
        orig_direction = original["direction"]
        orig_type = original["type"]
        amount = int(original["amount_pence"])

        # The reversal applies the opposite direction to the SAME account.
        reversal_direction = "outgoing" if orig_direction == "incoming" else "incoming"

        # For deposits/withdrawals there is no paired account.
        # For transfers there is a paired transaction via related_transaction_id.
        paired_txn_id = original["related_transaction_id"]
        paired_account_id: int | None = None
        if orig_type == "transfer" and paired_txn_id is not None:
            paired = conn.execute(
                "SELECT account_id FROM transactions WHERE id = ?", (paired_txn_id,)
            ).fetchone()
            if paired is not None:
                paired_account_id = int(paired["account_id"])

        # Sufficient-funds check: whichever account is *debited* by the reversal
        # must have enough.
        # - On the caller's account: reversal debits if reversal_direction == 'outgoing'.
        # - On the paired account: the paired reversal moves opposite to the caller's
        #   reversal, so debits the paired account when the caller's reversal is incoming.
        caller_debit = reversal_direction == "outgoing"
        if caller_debit:
            if _balance_pence(conn, account_id) < amount:
                raise BusinessRuleError("insufficient funds for reversal")
        if paired_account_id is not None:
            paired_debit = reversal_direction == "incoming"  # opposite of caller
            if paired_debit:
                if _balance_pence(conn, paired_account_id) < amount:
                    raise BusinessRuleError("recipient has insufficient funds for reversal")

        # Mark the originals as reversed.
        conn.execute(
            "UPDATE transactions SET status = 'reversed' WHERE id = ?",
            (transaction_id,),
        )
        if paired_txn_id is not None:
            conn.execute(
                "UPDATE transactions SET status = 'reversed' WHERE id = ?",
                (paired_txn_id,),
            )

        # Insert the reversal rows.
        reversal_id = _insert_txn(
            conn,
            account_id,
            "reversal",
            reversal_direction,
            amount,
            "completed",
            reverses_transaction_id=transaction_id,
        )
        paired_reversal_id: int | None = None
        if paired_account_id is not None:
            paired_reversal_direction = "incoming" if reversal_direction == "outgoing" else "outgoing"
            paired_reversal_id = _insert_txn(
                conn,
                paired_account_id,
                "reversal",
                paired_reversal_direction,
                amount,
                "completed",
                reverses_transaction_id=paired_txn_id,
                related_transaction_id=reversal_id,
            )
            conn.execute(
                "UPDATE transactions SET related_transaction_id = ? WHERE id = ?",
                (paired_reversal_id, reversal_id),
            )

        return reversal_id, transaction_id, "completed"


# -------------------------------------------------------------- Transactions
def list_transactions(account_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id AS transaction_id, type, amount_pence, direction, status, created_at
        FROM transactions
        WHERE account_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (account_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_account(account_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT id AS account_id, balance_pence, currency FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError("account not found")
    balance = _balance_pence(conn, account_id)
    return {
        "account_id": row["account_id"],
        "balance_pence": balance,
        "currency": row["currency"],
    }


# -------------------------------------------------------------- Internals
def _insert_txn(
    conn: sqlite3.Connection,
    account_id: int,
    type_: str,
    direction: str,
    amount: int,
    status: str,
    reverses_transaction_id: int | None = None,
    related_transaction_id: int | None = None,
) -> int:
    # Use a UUID-ish suffix in created_at ordering is by (created_at DESC, id DESC).
    cur = conn.execute(
        """
        INSERT INTO transactions
            (account_id, type, direction, amount_pence, status,
             reverses_transaction_id, related_transaction_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            type_,
            direction,
            amount,
            status,
            reverses_transaction_id,
            related_transaction_id,
            _now_iso(),
        ),
    )
    return int(cur.lastrowid)


# A stable uuid helper kept for future use; not currently invoked.
def _uuid() -> str:
    return str(uuid.uuid4())