from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator

from .config import settings


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    balance_pence INTEGER NOT NULL DEFAULT 0 CHECK (balance_pence >= 0),
    currency TEXT NOT NULL DEFAULT 'GBP',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('deposit', 'withdrawal', 'transfer', 'reversal')),
    amount_pence INTEGER NOT NULL CHECK (amount_pence > 0),
    status TEXT NOT NULL CHECK (status IN ('completed', 'reversed')),
    created_at TEXT NOT NULL,
    initiator_user_id INTEGER NOT NULL,
    counterparty_user_id INTEGER,
    reverses_transaction_id TEXT,
    reversed_by_transaction_id TEXT UNIQUE,
    FOREIGN KEY (initiator_user_id) REFERENCES users(id),
    FOREIGN KEY (counterparty_user_id) REFERENCES users(id),
    FOREIGN KEY (reverses_transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (reversed_by_transaction_id) REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    amount_pence INTEGER NOT NULL CHECK (amount_pence != 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_reverses ON transactions(reverses_transaction_id);
CREATE INDEX IF NOT EXISTS idx_ledger_account_created ON ledger_entries(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_transaction ON ledger_entries(transaction_id);
"""


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection for a request.

    isolation_level=None enables autocommit mode, letting service functions start
    explicit BEGIN IMMEDIATE transactions for balance-changing operations.
    """
    database_path = Path(settings.DATABASE_PATH)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        database_path,
        timeout=30,
        isolation_level=None,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize_database() -> None:
    """Create tables and indexes if they do not already exist."""
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_SQL)


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency returning a request-scoped SQLite connection."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def immediate_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Run operations inside an immediate SQLite transaction.

    BEGIN IMMEDIATE obtains the write lock up front, making balance updates,
    ledger inserts, reversals and daily-limit checks atomic against other writers.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
