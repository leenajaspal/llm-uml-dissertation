"""Business logic for the payments application.

Every money-moving operation:
  * runs inside a single serialised write transaction,
  * validates preconditions (funds, daily cap, ownership) atomically,
  * records the operation in ``transactions`` and writes *balanced*
    ``ledger_entries`` (their amounts sum to zero),
  * derives balances from the ledger so history and balance can never diverge.
"""
from datetime import datetime, timezone

from config import CURRENCY, DAILY_LIMIT_PENCE
from database import read_connection, write_transaction
from errors import AuthError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)

COMPLETED = "completed"
REVERSED = "reversed"


# --- small helpers -----------------------------------------------------------


def _now():
    dt = datetime.now(timezone.utc)
    return dt.isoformat(), dt.strftime("%Y-%m-%d")


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _user_account(conn, user_id: int):
    row = conn.execute(
        "SELECT id, currency, kind FROM accounts WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError("Account not found")
    return row


def _system_account(conn):
    return conn.execute("SELECT id FROM accounts WHERE kind = 'system'").fetchone()


def _balance(conn, account_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_pence), 0) AS bal "
        "FROM ledger_entries WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    return row["bal"]


def _daily_outgoing(conn, user_id: int, date_str: str) -> int:
    """Money already moved out by this user today (withdrawals + transfers).

    Reversed transactions are excluded (the money came back), and reversals
    themselves never count toward the cap.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_pence), 0) AS total FROM transactions "
        "WHERE initiator_user_id = ? "
        "AND type IN ('withdrawal', 'transfer') "
        "AND status = ? AND created_at_date = ?",
        (user_id, COMPLETED, date_str),
    ).fetchone()
    return row["total"]


def _insert_txn(conn, ttype, status, amount, initiator, reverses, created_at, date_str):
    cur = conn.execute(
        "INSERT INTO transactions "
        "(type, status, amount_pence, initiator_user_id, reverses_transaction_id, "
        " created_at, created_at_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ttype, status, amount, initiator, reverses, created_at, date_str),
    )
    return cur.lastrowid


def _insert_entry(conn, txn_id, account_id, signed_amount, created_at):
    conn.execute(
        "INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, created_at) "
        "VALUES (?, ?, ?, ?)",
        (txn_id, account_id, signed_amount, created_at),
    )


# --- auth --------------------------------------------------------------------


def register_user(email: str, password: str) -> dict:
    import sqlite3

    email = _normalise_email(email)
    pw_hash = hash_password(password)
    created_at, _ = _now()
    with write_transaction() as conn:
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise ConflictError("Email already registered")
        try:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, pw_hash, created_at),
            )
        except sqlite3.IntegrityError:
            raise ConflictError("Email already registered")
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO accounts (user_id, currency, kind, created_at) "
            "VALUES (?, ?, 'user', ?)",
            (user_id, CURRENCY, created_at),
        )
    return {"user_id": user_id, "email": email}


def login_user(email: str, password: str) -> dict:
    email = _normalise_email(email)
    with read_connection() as conn:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()

    if user is None:
        # Verify against a dummy hash so timing does not reveal whether the
        # email exists, then fail with the same generic error.
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise AuthError("Invalid email or password")

    if not verify_password(password, user["password_hash"]):
        raise AuthError("Invalid email or password")

    return {"access_token": create_access_token(user["id"])}


# --- account -----------------------------------------------------------------


def get_account(user_id: int) -> dict:
    with read_connection() as conn:
        acc = _user_account(conn, user_id)
        balance = _balance(conn, acc["id"])
    return {
        "account_id": acc["id"],
        "balance_pence": balance,
        "currency": acc["currency"],
    }


# --- deposits / withdrawals --------------------------------------------------


def deposit(user_id: int, amount_pence: int) -> dict:
    created_at, date_str = _now()
    with write_transaction() as conn:
        acc = _user_account(conn, user_id)
        system = _system_account(conn)
        txn_id = _insert_txn(
            conn, "deposit", COMPLETED, amount_pence, user_id, None, created_at, date_str
        )
        _insert_entry(conn, txn_id, acc["id"], amount_pence, created_at)
        _insert_entry(conn, txn_id, system["id"], -amount_pence, created_at)
        balance = _balance(conn, acc["id"])
    return {"transaction_id": txn_id, "status": COMPLETED, "balance_pence": balance}


def withdraw(user_id: int, amount_pence: int) -> dict:
    created_at, date_str = _now()
    with write_transaction() as conn:
        acc = _user_account(conn, user_id)
        system = _system_account(conn)

        outgoing = _daily_outgoing(conn, user_id, date_str)
        if outgoing + amount_pence > DAILY_LIMIT_PENCE:
            raise ConflictError("Daily outgoing limit exceeded")

        balance = _balance(conn, acc["id"])
        if balance < amount_pence:
            raise ConflictError("Insufficient funds")

        txn_id = _insert_txn(
            conn, "withdrawal", COMPLETED, amount_pence, user_id, None, created_at, date_str
        )
        _insert_entry(conn, txn_id, acc["id"], -amount_pence, created_at)
        _insert_entry(conn, txn_id, system["id"], amount_pence, created_at)
        new_balance = balance - amount_pence
    return {"transaction_id": txn_id, "status": COMPLETED, "balance_pence": new_balance}


# --- transfers ---------------------------------------------------------------


def transfer(user_id: int, recipient_email: str, amount_pence: int) -> dict:
    recipient_email = _normalise_email(recipient_email)
    created_at, date_str = _now()
    with write_transaction() as conn:
        sender_acc = _user_account(conn, user_id)

        recipient = conn.execute(
            "SELECT id FROM users WHERE email = ?", (recipient_email,)
        ).fetchone()
        if recipient is None:
            raise NotFoundError("Recipient not found")
        if recipient["id"] == user_id:
            raise ValidationError("Cannot transfer to yourself")
        recipient_acc = _user_account(conn, recipient["id"])

        outgoing = _daily_outgoing(conn, user_id, date_str)
        if outgoing + amount_pence > DAILY_LIMIT_PENCE:
            raise ConflictError("Daily outgoing limit exceeded")

        balance = _balance(conn, sender_acc["id"])
        if balance < amount_pence:
            raise ConflictError("Insufficient funds")

        txn_id = _insert_txn(
            conn, "transfer", COMPLETED, amount_pence, user_id, None, created_at, date_str
        )
        _insert_entry(conn, txn_id, sender_acc["id"], -amount_pence, created_at)
        _insert_entry(conn, txn_id, recipient_acc["id"], amount_pence, created_at)
        new_balance = balance - amount_pence
    return {"transaction_id": txn_id, "status": COMPLETED, "balance_pence": new_balance}


# --- history -----------------------------------------------------------------


def list_transactions(user_id: int) -> list:
    with read_connection() as conn:
        acc = _user_account(conn, user_id)
        rows = conn.execute(
            "SELECT t.id AS tid, t.type AS type, t.status AS status, "
            "       t.created_at AS created_at, le.amount_pence AS amt "
            "FROM ledger_entries le "
            "JOIN transactions t ON t.id = le.transaction_id "
            "WHERE le.account_id = ? "
            "ORDER BY le.id DESC",
            (acc["id"],),
        ).fetchall()

    items = []
    for r in rows:
        amt = r["amt"]
        items.append(
            {
                "transaction_id": r["tid"],
                "type": r["type"],
                "amount_pence": abs(amt),
                "direction": "credit" if amt > 0 else "debit",
                "status": r["status"],
                "created_at": r["created_at"],
            }
        )
    return items


# --- reversal ----------------------------------------------------------------


def reverse_transaction(user_id: int, transaction_id: int) -> dict:
    created_at, date_str = _now()
    with write_transaction() as conn:
        txn = conn.execute(
            "SELECT id, type, status, amount_pence, initiator_user_id "
            "FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        if txn is None:
            raise NotFoundError("Transaction not found")
        if txn["initiator_user_id"] != user_id:
            raise ForbiddenError("You can only reverse your own transactions")
        if txn["type"] == "reversal":
            raise ConflictError("A reversal cannot itself be reversed")
        if txn["status"] != COMPLETED:
            raise ConflictError("Transaction is not in a reversible state")
        if conn.execute(
            "SELECT id FROM transactions WHERE reverses_transaction_id = ?",
            (transaction_id,),
        ).fetchone():
            raise ConflictError("Transaction has already been reversed")

        entries = conn.execute(
            "SELECT le.account_id AS account_id, le.amount_pence AS amount_pence, "
            "       a.kind AS kind "
            "FROM ledger_entries le JOIN accounts a ON a.id = le.account_id "
            "WHERE le.transaction_id = ?",
            (transaction_id,),
        ).fetchall()

        # Reversing pulls money back. Never let a *user* account go negative;
        # if the recipient has already spent the funds, refuse rather than
        # create a negative balance. (The system account may go negative.)
        for e in entries:
            reverse_amount = -e["amount_pence"]
            if e["kind"] == "user":
                if _balance(conn, e["account_id"]) + reverse_amount < 0:
                    raise ConflictError(
                        "Reversal would overdraw an account; the funds are no "
                        "longer available"
                    )

        reversal_id = _insert_txn(
            conn,
            "reversal",
            COMPLETED,
            txn["amount_pence"],
            user_id,
            transaction_id,
            created_at,
            date_str,
        )
        for e in entries:
            _insert_entry(conn, reversal_id, e["account_id"], -e["amount_pence"], created_at)

        conn.execute(
            "UPDATE transactions SET status = ? WHERE id = ?", (REVERSED, transaction_id)
        )

    return {
        "transaction_id": reversal_id,
        "reverses_transaction_id": transaction_id,
        "status": COMPLETED,
    }
