"""SQLite database setup and connection management."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("WALLET_DB_PATH", "wallet.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES users(id),
    currency TEXT NOT NULL DEFAULT 'GBP',
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('deposit','withdrawal','transfer','reversal')),
    status TEXT NOT NULL CHECK (status IN ('completed','reversed')),
    reverses_transaction_id INTEGER REFERENCES transactions(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    amount_pence INTEGER NOT NULL CHECK (amount_pence > 0),
    direction TEXT NOT NULL CHECK (direction IN ('debit','credit')),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_account ON ledger_entries(account_id);
CREATE INDEX IF NOT EXISTS idx_ledger_transaction ON ledger_entries(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit; we manage txns
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_db():
    """Yield a connection wrapped in a single transaction (atomic)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create schema and ensure the system account exists."""
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT id FROM accounts WHERE is_system = 1"
        ).fetchone()
        if row is None:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO accounts (user_id, currency, is_system, created_at) "
                "VALUES (NULL, 'GBP', 1, ?)",
                (now,),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def get_system_account_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM accounts WHERE is_system = 1").fetchone()
    if row is None:
        # Should never happen after init_db, but be defensive.
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO accounts (user_id, currency, is_system, created_at) "
            "VALUES (NULL, 'GBP', 1, ?)",
            (now,),
        )
        return cur.lastrowid
    return row["id"]