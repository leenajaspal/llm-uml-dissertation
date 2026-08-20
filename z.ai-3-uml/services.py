from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

import sqlite3
from fastapi import HTTPException

# £1,000 in pence — combined daily limit on withdrawals + transfers.
DAILY_LIMIT_PENCE: int = 100_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_user_account(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM accounts WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return row


def get_system_account(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM accounts WHERE is_system = 1"
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=500, detail="System account not configured"
        )
    return row


def compute_balance(conn: sqlite3.Connection, account_id: int) -> int:
    """Derived balance: credits minus debits across the account's ledger entries."""
    row = conn.execute(
        """
        SELECT COALESCE(
            SUM(CASE WHEN direction='credit' THEN amount_pence
                     ELSE -amount_pence END), 0
        ) AS balance
        FROM ledger_entries
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return int(row["balance"])


def daily_outflow_total(
    conn: sqlite3.Connection, account_id: int, now: datetime
) -> int:
    """Sum of this account's debit entries on completed transfers/withdrawals
    created in the last 24 hours. Reversed transfers are excluded (funds
    returned). Deposits and reversals never count."""
    cutoff = (now - timedelta(hours=24)).isoformat()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(le.amount_pence), 0) AS total
        FROM ledger_entries le
        JOIN transactions t ON le.transaction_id = t.transaction_id
        WHERE le.account_id = ?
          AND le.direction = 'debit'
          AND t.type IN ('transfer','withdrawal')
          AND t.status = 'completed'
          AND t.created_at >= ?
        """,
        (account_id, cutoff),
    ).fetchone()
    return int(row["total"])


@contextmanager
def db_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Atomic write unit. Acquires a write lock immediately (BEGIN IMMEDIATE)
    so concurrent writers serialise and balance checks are consistent."""
    conn.execute("BEGIN IMMEDIATE")
    committed = False
    try:
        yield
        conn.execute("COMMIT")
        committed = True
    except Exception:
        if not committed:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
        raise


def insert_transaction(
    conn: sqlite3.Connection,
    type_: str,
    status: str,
    created_at: str,
    reverses_transaction_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO transactions (type, status, created_at, reverses_transaction_id) "
        "VALUES (?,?,?,?)",
        (type_, status, created_at, reverses_transaction_id),
    )
    return int(cur.lastrowid)


def insert_ledger_entry(
    conn: sqlite3.Connection,
    transaction_id: int,
    account_id: int,
    amount_pence: int,
    direction: str,
) -> None:
    conn.execute(
        "INSERT INTO ledger_entries "
        "(transaction_id, account_id, amount_pence, direction) "
        "VALUES (?,?,?,?)",
        (transaction_id, account_id, amount_pence, direction),
    )