import os
import sqlite3
from typing import Iterator

DB_PATH = os.environ.get("WALLET_DB_PATH", "wallet.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    currency TEXT NOT NULL DEFAULT 'GBP',
    is_system INTEGER NOT NULL DEFAULT 0,
    CHECK (is_system IN (0, 1))
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('deposit','withdrawal','transfer','reversal')),
    status TEXT NOT NULL CHECK (status IN ('completed','reversed')),
    created_at TEXT NOT NULL,
    reverses_transaction_id INTEGER
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    ledger_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(transaction_id),
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    amount_pence INTEGER NOT NULL CHECK (amount_pence > 0),
    direction TEXT NOT NULL CHECK (direction IN ('debit','credit'))
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_account ON ledger_entries(account_id);
CREATE INDEX IF NOT EXISTS idx_ledger_transaction ON ledger_entries(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_reverses ON transactions(reverses_transaction_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,
        isolation_level=None,  # autocommit; we manage transactions explicitly
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT account_id FROM accounts WHERE is_system = 1"
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO accounts (user_id, currency, is_system) "
                "VALUES (NULL, 'GBP', 1)"
            )
    finally:
        conn.close()