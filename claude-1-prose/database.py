"""SQLite access layer.

Design notes for money correctness:

* Balances are never stored as a mutable column. An account's balance is the
  SUM of its immutable ``ledger_entries``. History is therefore the single
  source of truth and a balance can never disagree with what happened.

* Every transaction inserts *balanced* ledger entries (they sum to zero),
  using a hidden ``system`` account as the counterparty for deposits and
  withdrawals. Consequently the grand total of all ledger entries is always
  exactly zero: money can never be created, destroyed or double counted.

* All state-changing operations run inside ``write_transaction`` which issues
  ``BEGIN IMMEDIATE``. SQLite allows a single writer at a time, so the write
  lock serialises concurrent mutations and makes every check-then-write
  (e.g. "do you have enough funds?") atomic. WAL mode lets reads proceed
  concurrently without blocking the writer.
"""
import sqlite3
from contextlib import contextmanager

from config import CURRENCY, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER UNIQUE,                 -- NULL for the system account
    currency   TEXT NOT NULL DEFAULT 'GBP',
    kind       TEXT NOT NULL DEFAULT 'user',   -- 'user' | 'system'
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    type                    TEXT NOT NULL,      -- deposit|withdrawal|transfer|reversal
    status                  TEXT NOT NULL,      -- completed|reversed
    amount_pence            INTEGER NOT NULL,   -- positive magnitude
    initiator_user_id       INTEGER,
    reverses_transaction_id INTEGER,
    created_at              TEXT NOT NULL,
    created_at_date         TEXT NOT NULL,      -- 'YYYY-MM-DD' (UTC) for the daily cap
    FOREIGN KEY (initiator_user_id) REFERENCES users (id),
    FOREIGN KEY (reverses_transaction_id) REFERENCES transactions (id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL,
    account_id     INTEGER NOT NULL,
    amount_pence   INTEGER NOT NULL,   -- signed: +credit (money in), -debit (money out)
    created_at     TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_account ON ledger_entries (account_id);
CREATE INDEX IF NOT EXISTS idx_ledger_txn ON ledger_entries (transaction_id);
CREATE INDEX IF NOT EXISTS idx_txn_initiator_date
    ON transactions (initiator_user_id, created_at_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_txn_reverses
    ON transactions (reverses_transaction_id)
    WHERE reverses_transaction_id IS NOT NULL;
"""


def get_connection() -> sqlite3.Connection:
    """Open a new connection configured for safe, concurrent use."""
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def write_transaction():
    """Serialised read-modify-write transaction (BEGIN IMMEDIATE)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def read_connection():
    """Read-only connection (autocommit)."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema (idempotent) and ensure the system account exists."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT id FROM accounts WHERE kind='system'").fetchone()
        if row is None:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO accounts (user_id, currency, kind, created_at) "
                "VALUES (NULL, ?, 'system', ?)",
                (CURRENCY, now),
            )
    finally:
        conn.close()


def verify_ledger_integrity() -> int:
    """Return the grand total of every ledger entry.

    Because the ledger is strict double-entry, this must always be exactly 0.
    Exposed for tests / operational health checks, not via the HTTP API.
    """
    with read_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_pence), 0) AS total FROM ledger_entries"
        ).fetchone()
    return row["total"]
