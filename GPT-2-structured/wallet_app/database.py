"""SQLite database setup and request-scoped connection handling."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from .config import CURRENCY, DATABASE_URL, SYSTEM_ACCOUNT_ID
from .security import iso_now


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    currency TEXT NOT NULL CHECK (currency = 'GBP'),
    is_system INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0, 1)),
    created_at TEXT NOT NULL,
    CHECK (
        (is_system = 1 AND user_id IS NULL)
        OR
        (is_system = 0 AND user_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_single_system
ON accounts(is_system)
WHERE is_system = 1;

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('deposit', 'withdrawal', 'transfer', 'reversal')),
    status TEXT NOT NULL CHECK (status IN ('completed', 'reversed')),
    reversed_transaction_id TEXT UNIQUE REFERENCES transactions(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    amount_pence INTEGER NOT NULL CHECK (amount_pence > 0),
    direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_transaction
ON ledger_entries(transaction_id);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_account
ON ledger_entries(account_id);

CREATE INDEX IF NOT EXISTS idx_transactions_created_at
ON transactions(created_at);

CREATE TABLE IF NOT EXISTS access_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_access_tokens_user
ON access_tokens(user_id);
"""


def connect_db(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DATABASE_URL, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(path: str | None = None) -> None:
    conn = connect_db(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            """
            INSERT OR IGNORE INTO accounts (id, user_id, currency, is_system, created_at)
            VALUES (?, NULL, ?, 1, ?)
            """,
            (SYSTEM_ACCOUNT_ID, CURRENCY, iso_now()),
        )
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = connect_db()
    try:
        yield conn
    finally:
        conn.close()
