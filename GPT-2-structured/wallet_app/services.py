"""Core wallet operations and ledger writes."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status

from .config import CURRENCY, ROLLING_LIMIT_HOURS, ROLLING_LIMIT_PENCE, SYSTEM_ACCOUNT_ID
from .security import (
    create_access_token,
    hash_password,
    hash_token,
    iso_from_datetime,
    iso_now,
    now_utc,
    token_expiry_iso,
    verify_password,
)


@contextmanager
def atomic(conn: sqlite3.Connection) -> Iterator[None]:
    """Run a block inside a SQLite transaction, rolling back on any error."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _new_id() -> str:
    return str(uuid.uuid4())


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _account_for_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    account = conn.execute(
        "SELECT id, user_id, currency FROM accounts WHERE user_id = ? AND is_system = 0",
        (user_id,),
    ).fetchone()
    if account is None:
        raise HTTPException(status_code=500, detail="Account not found for user")
    return account


def _user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, email, password_salt, password_hash, created_at FROM users WHERE email = ?",
        (email,),
    ).fetchone()


def _account_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT a.id, a.user_id, a.currency, u.email
        FROM accounts a
        JOIN users u ON u.id = a.user_id
        WHERE u.email = ? AND a.is_system = 0
        """,
        (email,),
    ).fetchone()


def account_balance(conn: sqlite3.Connection, account_id: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(
            SUM(CASE direction WHEN 'credit' THEN amount_pence ELSE -amount_pence END),
            0
        ) AS balance_pence
        FROM ledger_entries
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return int(row["balance_pence"] or 0)


def _rolling_outgoing_total(conn: sqlite3.Connection, account_id: str, created_at_cutoff: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(le.amount_pence), 0) AS total_pence
        FROM ledger_entries le
        JOIN transactions t ON t.id = le.transaction_id
        WHERE le.account_id = ?
          AND le.direction = 'debit'
          AND t.type IN ('withdrawal', 'transfer')
          AND t.created_at >= ?
        """,
        (account_id, created_at_cutoff),
    ).fetchone()
    return int(row["total_pence"] or 0)


def _check_rolling_limit(
    conn: sqlite3.Connection,
    account_id: str,
    amount_pence: int,
    created_at_cutoff: str,
) -> None:
    used_pence = _rolling_outgoing_total(conn, account_id, created_at_cutoff)
    if used_pence + amount_pence > ROLLING_LIMIT_PENCE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rolling 24-hour transfer and withdrawal limit exceeded",
        )


def _create_transaction(
    conn: sqlite3.Connection,
    *,
    transaction_type: str,
    amount_pence: int,
    debit_account_id: str,
    credit_account_id: str,
    created_at: str,
    reversed_transaction_id: str | None = None,
) -> str:
    if debit_account_id == credit_account_id:
        raise HTTPException(status_code=400, detail="Ledger entries must use two different accounts")

    transaction_id = _new_id()
    debit_entry_id = _new_id()
    credit_entry_id = _new_id()

    conn.execute(
        """
        INSERT INTO transactions (id, type, status, reversed_transaction_id, created_at)
        VALUES (?, ?, 'completed', ?, ?)
        """,
        (transaction_id, transaction_type, reversed_transaction_id, created_at),
    )
    conn.execute(
        """
        INSERT INTO ledger_entries (id, transaction_id, account_id, amount_pence, direction, created_at)
        VALUES (?, ?, ?, ?, 'debit', ?)
        """,
        (debit_entry_id, transaction_id, debit_account_id, amount_pence, created_at),
    )
    conn.execute(
        """
        INSERT INTO ledger_entries (id, transaction_id, account_id, amount_pence, direction, created_at)
        VALUES (?, ?, ?, ?, 'credit', ?)
        """,
        (credit_entry_id, transaction_id, credit_account_id, amount_pence, created_at),
    )
    return transaction_id


def register_user(conn: sqlite3.Connection, email: str, password: str) -> dict[str, Any]:
    user_id = _new_id()
    account_id = _new_id()
    created_at = iso_now()
    salt_hex, password_hash_hex = hash_password(password)

    try:
        with atomic(conn):
            conn.execute(
                """
                INSERT INTO users (id, email, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, email, salt_hex, password_hash_hex, created_at),
            )
            conn.execute(
                """
                INSERT INTO accounts (id, user_id, currency, is_system, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (account_id, user_id, CURRENCY, created_at),
            )
    except sqlite3.IntegrityError as exc:
        if "users.email" in str(exc) or "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="Email is already registered") from exc
        raise

    return {"user_id": user_id, "email": email}


def login(conn: sqlite3.Connection, email: str, password: str) -> dict[str, str]:
    user = _user_by_email(conn, email)
    if user is None or not verify_password(password, user["password_salt"], user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token()
    with atomic(conn):
        conn.execute(
            """
            INSERT INTO access_tokens (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (hash_token(access_token), user["id"], iso_now(), token_expiry_iso()),
        )
    return {"access_token": access_token}


def current_user_from_token(conn: sqlite3.Connection, bearer_token: str | None) -> sqlite3.Row:
    if not bearer_token:
        raise _not_authenticated()

    token_hash = hash_token(bearer_token)
    row = conn.execute(
        """
        SELECT u.id, u.email, u.created_at
        FROM access_tokens tok
        JOIN users u ON u.id = tok.user_id
        WHERE tok.token_hash = ? AND tok.expires_at > ?
        """,
        (token_hash, iso_now()),
    ).fetchone()
    if row is None:
        raise _not_authenticated()
    return row


def get_my_account(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    account = _account_for_user(conn, user_id)
    return {
        "account_id": account["id"],
        "balance_pence": account_balance(conn, account["id"]),
        "currency": account["currency"],
    }


def deposit(conn: sqlite3.Connection, user_id: str, amount_pence: int) -> dict[str, Any]:
    with atomic(conn):
        account = _account_for_user(conn, user_id)
        created_at = iso_now()
        transaction_id = _create_transaction(
            conn,
            transaction_type="deposit",
            amount_pence=amount_pence,
            debit_account_id=SYSTEM_ACCOUNT_ID,
            credit_account_id=account["id"],
            created_at=created_at,
        )
        balance_pence = account_balance(conn, account["id"])
    return {"transaction_id": transaction_id, "status": "completed", "balance_pence": balance_pence}


def withdraw(conn: sqlite3.Connection, user_id: str, amount_pence: int) -> dict[str, Any]:
    with atomic(conn):
        account = _account_for_user(conn, user_id)
        current_balance = account_balance(conn, account["id"])
        if current_balance < amount_pence:
            raise HTTPException(status_code=409, detail="Insufficient funds")

        request_time = now_utc()
        cutoff = iso_from_datetime(request_time - timedelta(hours=ROLLING_LIMIT_HOURS))
        _check_rolling_limit(conn, account["id"], amount_pence, cutoff)

        created_at = iso_from_datetime(request_time)
        transaction_id = _create_transaction(
            conn,
            transaction_type="withdrawal",
            amount_pence=amount_pence,
            debit_account_id=account["id"],
            credit_account_id=SYSTEM_ACCOUNT_ID,
            created_at=created_at,
        )
        balance_pence = account_balance(conn, account["id"])
    return {"transaction_id": transaction_id, "status": "completed", "balance_pence": balance_pence}


def transfer(
    conn: sqlite3.Connection,
    user_id: str,
    sender_email: str,
    recipient_email: str,
    amount_pence: int,
) -> dict[str, Any]:
    if sender_email == recipient_email:
        raise HTTPException(status_code=400, detail="Cannot transfer to your own account")

    with atomic(conn):
        sender_account = _account_for_user(conn, user_id)
        recipient_account = _account_by_email(conn, recipient_email)
        if recipient_account is None:
            raise HTTPException(status_code=404, detail="Recipient not found")

        current_balance = account_balance(conn, sender_account["id"])
        if current_balance < amount_pence:
            raise HTTPException(status_code=409, detail="Insufficient funds")

        request_time = now_utc()
        cutoff = iso_from_datetime(request_time - timedelta(hours=ROLLING_LIMIT_HOURS))
        _check_rolling_limit(conn, sender_account["id"], amount_pence, cutoff)

        created_at = iso_from_datetime(request_time)
        transaction_id = _create_transaction(
            conn,
            transaction_type="transfer",
            amount_pence=amount_pence,
            debit_account_id=sender_account["id"],
            credit_account_id=recipient_account["id"],
            created_at=created_at,
        )
        balance_pence = account_balance(conn, sender_account["id"])
    return {"transaction_id": transaction_id, "status": "completed", "balance_pence": balance_pence}


def transactions_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    account = _account_for_user(conn, user_id)
    rows = conn.execute(
        """
        SELECT
            t.id AS transaction_id,
            t.type AS type,
            le.amount_pence AS amount_pence,
            le.direction AS direction,
            t.status AS status,
            t.created_at AS created_at
        FROM transactions t
        JOIN ledger_entries le ON le.transaction_id = t.id
        WHERE le.account_id = ?
        ORDER BY t.created_at DESC, t.id DESC
        """,
        (account["id"],),
    ).fetchall()
    return [dict(row) for row in rows]


def reverse_transfer(conn: sqlite3.Connection, user_id: str, transaction_id: str) -> dict[str, str]:
    with atomic(conn):
        sender_account = _account_for_user(conn, user_id)

        original = conn.execute(
            """
            SELECT t.id, t.status, t.type
            FROM transactions t
            JOIN ledger_entries le ON le.transaction_id = t.id
            WHERE t.id = ?
              AND t.type = 'transfer'
              AND le.account_id = ?
              AND le.direction = 'debit'
            """,
            (transaction_id, sender_account["id"]),
        ).fetchone()
        if original is None:
            raise HTTPException(status_code=404, detail="Transfer not found")
        if original["status"] != "completed":
            raise HTTPException(status_code=409, detail="Transfer cannot be reversed")

        entries = conn.execute(
            """
            SELECT account_id, amount_pence, direction
            FROM ledger_entries
            WHERE transaction_id = ?
            ORDER BY direction
            """,
            (transaction_id,),
        ).fetchall()
        if len(entries) != 2:
            raise HTTPException(status_code=500, detail="Original transaction ledger is invalid")

        debit_entry = next((entry for entry in entries if entry["direction"] == "debit"), None)
        credit_entry = next((entry for entry in entries if entry["direction"] == "credit"), None)
        if debit_entry is None or credit_entry is None:
            raise HTTPException(status_code=500, detail="Original transaction ledger is invalid")
        if debit_entry["account_id"] != sender_account["id"]:
            raise HTTPException(status_code=404, detail="Transfer not found")
        if debit_entry["amount_pence"] != credit_entry["amount_pence"]:
            raise HTTPException(status_code=500, detail="Original transaction ledger is invalid")

        amount_pence = int(debit_entry["amount_pence"])
        recipient_account_id = str(credit_entry["account_id"])

        if account_balance(conn, recipient_account_id) < amount_pence:
            raise HTTPException(status_code=409, detail="Recipient has insufficient funds to reverse transfer")

        created_at = iso_now()
        try:
            reversal_id = _create_transaction(
                conn,
                transaction_type="reversal",
                amount_pence=amount_pence,
                debit_account_id=recipient_account_id,
                credit_account_id=sender_account["id"],
                created_at=created_at,
                reversed_transaction_id=transaction_id,
            )
            conn.execute(
                "UPDATE transactions SET status = 'reversed' WHERE id = ?",
                (transaction_id,),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Transfer cannot be reversed") from exc

    return {
        "transaction_id": reversal_id,
        "reverses_transaction_id": transaction_id,
        "status": "completed",
    }
