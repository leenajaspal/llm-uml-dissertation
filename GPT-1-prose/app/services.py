from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, time, timezone
from typing import Iterable

from fastapi import HTTPException, status

from .config import settings
from .database import immediate_transaction
from .security import create_access_token, hash_password, verify_password


COMPLETED = "completed"
REVERSED = "reversed"
INCOMING = "incoming"
OUTGOING = "outgoing"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def start_of_utc_day_iso() -> str:
    today = datetime.now(timezone.utc).date()
    return datetime.combine(today, time.min, tzinfo=timezone.utc).isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
        (normalize_email(email),),
    ).fetchone()


def get_account_by_user_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    account = conn.execute(
        "SELECT id, user_id, balance_pence, currency FROM accounts WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


def register_user(conn: sqlite3.Connection, email: str, password: str) -> dict[str, object]:
    normalized_email = normalize_email(email)
    created_at = utc_now_iso()
    try:
        with immediate_transaction(conn):
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (normalized_email, hash_password(password), created_at),
            )
            user_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO accounts (user_id, balance_pence, currency, created_at) VALUES (?, ?, ?, ?)",
                (user_id, 0, settings.CURRENCY, created_at),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    return {"user_id": user_id, "email": normalized_email}


def authenticate_user(conn: sqlite3.Connection, email: str, password: str) -> dict[str, str]:
    user = get_user_by_email(conn, email)
    if user is None or not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": create_access_token(int(user["id"]))}


def account_response(conn: sqlite3.Connection, user_id: int) -> dict[str, object]:
    account = get_account_by_user_id(conn, user_id)
    return {
        "account_id": int(account["id"]),
        "balance_pence": int(account["balance_pence"]),
        "currency": account["currency"],
    }


def _insert_transaction(
    conn: sqlite3.Connection,
    *,
    transaction_type: str,
    amount_pence: int,
    initiator_user_id: int,
    created_at: str,
    counterparty_user_id: int | None = None,
    reverses_transaction_id: str | None = None,
) -> str:
    transaction_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO transactions (
            id, type, amount_pence, status, created_at,
            initiator_user_id, counterparty_user_id, reverses_transaction_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            transaction_type,
            amount_pence,
            COMPLETED,
            created_at,
            initiator_user_id,
            counterparty_user_id,
            reverses_transaction_id,
        ),
    )
    return transaction_id


def _insert_ledger_entry(
    conn: sqlite3.Connection,
    *,
    transaction_id: str,
    account_id: int,
    amount_pence: int,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ledger_entries (transaction_id, account_id, amount_pence, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (transaction_id, account_id, amount_pence, created_at),
    )


def _current_balance(conn: sqlite3.Connection, account_id: int) -> int:
    row = conn.execute(
        "SELECT balance_pence FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return int(row["balance_pence"])


def _assert_daily_move_limit(conn: sqlite3.Connection, account_id: int, amount_pence: int) -> None:
    """Enforce the daily money-out cap for withdrawals and outgoing transfers."""
    start = start_of_utc_day_iso()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(-le.amount_pence), 0) AS moved_today
        FROM ledger_entries AS le
        JOIN transactions AS t ON t.id = le.transaction_id
        WHERE le.account_id = ?
          AND le.amount_pence < 0
          AND t.type IN ('withdrawal', 'transfer')
          AND t.status IN ('completed', 'reversed')
          AND t.created_at >= ?
        """,
        (account_id, start),
    ).fetchone()
    moved_today = int(row["moved_today"] or 0)
    if moved_today + amount_pence > settings.DAILY_MOVE_LIMIT_PENCE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Daily movement limit of {settings.DAILY_MOVE_LIMIT_PENCE} pence exceeded",
        )


def _debit_account(conn: sqlite3.Connection, account_id: int, amount_pence: int) -> None:
    cursor = conn.execute(
        """
        UPDATE accounts
        SET balance_pence = balance_pence - ?
        WHERE id = ? AND balance_pence >= ?
        """,
        (amount_pence, account_id, amount_pence),
    )
    if cursor.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient funds")


def _credit_account(conn: sqlite3.Connection, account_id: int, amount_pence: int) -> None:
    conn.execute(
        "UPDATE accounts SET balance_pence = balance_pence + ? WHERE id = ?",
        (amount_pence, account_id),
    )


def create_deposit(conn: sqlite3.Connection, user_id: int, amount_pence: int) -> dict[str, object]:
    created_at = utc_now_iso()
    with immediate_transaction(conn):
        account = get_account_by_user_id(conn, user_id)
        transaction_id = _insert_transaction(
            conn,
            transaction_type="deposit",
            amount_pence=amount_pence,
            initiator_user_id=user_id,
            created_at=created_at,
        )
        _credit_account(conn, int(account["id"]), amount_pence)
        _insert_ledger_entry(
            conn,
            transaction_id=transaction_id,
            account_id=int(account["id"]),
            amount_pence=amount_pence,
            created_at=created_at,
        )
        balance = _current_balance(conn, int(account["id"]))
    return {"transaction_id": transaction_id, "status": COMPLETED, "balance_pence": balance}


def create_withdrawal(conn: sqlite3.Connection, user_id: int, amount_pence: int) -> dict[str, object]:
    created_at = utc_now_iso()
    with immediate_transaction(conn):
        account = get_account_by_user_id(conn, user_id)
        account_id = int(account["id"])
        _assert_daily_move_limit(conn, account_id, amount_pence)
        _debit_account(conn, account_id, amount_pence)
        transaction_id = _insert_transaction(
            conn,
            transaction_type="withdrawal",
            amount_pence=amount_pence,
            initiator_user_id=user_id,
            created_at=created_at,
        )
        _insert_ledger_entry(
            conn,
            transaction_id=transaction_id,
            account_id=account_id,
            amount_pence=-amount_pence,
            created_at=created_at,
        )
        balance = _current_balance(conn, account_id)
    return {"transaction_id": transaction_id, "status": COMPLETED, "balance_pence": balance}


def create_transfer(
    conn: sqlite3.Connection,
    sender_user_id: int,
    recipient_email: str,
    amount_pence: int,
) -> dict[str, object]:
    normalized_recipient_email = normalize_email(recipient_email)
    created_at = utc_now_iso()
    with immediate_transaction(conn):
        sender_account = get_account_by_user_id(conn, sender_user_id)
        sender_account_id = int(sender_account["id"])

        recipient_user = get_user_by_email(conn, normalized_recipient_email)
        if recipient_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
        recipient_user_id = int(recipient_user["id"])
        if recipient_user_id == sender_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot transfer to yourself")
        recipient_account = get_account_by_user_id(conn, recipient_user_id)
        recipient_account_id = int(recipient_account["id"])

        _assert_daily_move_limit(conn, sender_account_id, amount_pence)
        _debit_account(conn, sender_account_id, amount_pence)
        _credit_account(conn, recipient_account_id, amount_pence)

        transaction_id = _insert_transaction(
            conn,
            transaction_type="transfer",
            amount_pence=amount_pence,
            initiator_user_id=sender_user_id,
            counterparty_user_id=recipient_user_id,
            created_at=created_at,
        )
        _insert_ledger_entry(
            conn,
            transaction_id=transaction_id,
            account_id=sender_account_id,
            amount_pence=-amount_pence,
            created_at=created_at,
        )
        _insert_ledger_entry(
            conn,
            transaction_id=transaction_id,
            account_id=recipient_account_id,
            amount_pence=amount_pence,
            created_at=created_at,
        )
        balance = _current_balance(conn, sender_account_id)
    return {"transaction_id": transaction_id, "status": COMPLETED, "balance_pence": balance}


def list_user_transactions(conn: sqlite3.Connection, user_id: int) -> list[dict[str, object]]:
    account = get_account_by_user_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT
            t.id AS transaction_id,
            t.type AS type,
            t.amount_pence AS amount_pence,
            CASE WHEN le.amount_pence > 0 THEN ? ELSE ? END AS direction,
            t.status AS status,
            t.created_at AS created_at
        FROM ledger_entries AS le
        JOIN transactions AS t ON t.id = le.transaction_id
        WHERE le.account_id = ?
        ORDER BY t.created_at DESC, le.id DESC
        """,
        (INCOMING, OUTGOING, int(account["id"])),
    ).fetchall()
    return [
        {
            "transaction_id": row["transaction_id"],
            "type": row["type"],
            "amount_pence": int(row["amount_pence"]),
            "direction": row["direction"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _transaction_visible_to_account(
    conn: sqlite3.Connection,
    transaction_id: str,
    account_id: int,
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM ledger_entries
        WHERE transaction_id = ? AND account_id = ?
        LIMIT 1
        """,
        (transaction_id, account_id),
    ).fetchone()
    return row is not None


def _original_ledger_entries(conn: sqlite3.Connection, transaction_id: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT account_id, amount_pence
        FROM ledger_entries
        WHERE transaction_id = ?
        ORDER BY id ASC
        """,
        (transaction_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transaction has no ledger entries")
    return list(rows)


def reverse_transaction(
    conn: sqlite3.Connection,
    user_id: int,
    transaction_id: str,
) -> dict[str, object]:
    created_at = utc_now_iso()
    with immediate_transaction(conn):
        current_account = get_account_by_user_id(conn, user_id)
        current_account_id = int(current_account["id"])

        original = conn.execute(
            """
            SELECT id, type, amount_pence, status, initiator_user_id, reversed_by_transaction_id
            FROM transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()
        if original is None or not _transaction_visible_to_account(conn, transaction_id, current_account_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
        if original["type"] == "reversal":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reversal transactions cannot be reversed")
        if original["status"] != COMPLETED or original["reversed_by_transaction_id"] is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transaction has already been reversed")

        original_entries = _original_ledger_entries(conn, transaction_id)
        reversal_id = _insert_transaction(
            conn,
            transaction_type="reversal",
            amount_pence=int(original["amount_pence"]),
            initiator_user_id=user_id,
            created_at=created_at,
            reverses_transaction_id=transaction_id,
        )

        for entry in original_entries:
            account_id = int(entry["account_id"])
            reversal_amount = -int(entry["amount_pence"])
            cursor = conn.execute(
                """
                UPDATE accounts
                SET balance_pence = balance_pence + ?
                WHERE id = ? AND balance_pence + ? >= 0
                """,
                (reversal_amount, account_id, reversal_amount),
            )
            if cursor.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Reversal would overdraw one of the accounts",
                )
            _insert_ledger_entry(
                conn,
                transaction_id=reversal_id,
                account_id=account_id,
                amount_pence=reversal_amount,
                created_at=created_at,
            )

        conn.execute(
            """
            UPDATE transactions
            SET status = ?, reversed_by_transaction_id = ?
            WHERE id = ?
            """,
            (REVERSED, reversal_id, transaction_id),
        )
    return {
        "transaction_id": reversal_id,
        "reverses_transaction_id": transaction_id,
        "status": COMPLETED,
    }
