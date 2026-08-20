"""SQLite access layer.

Design notes
------------
* Connections run in autocommit mode (``isolation_level=None``) so that we can
  control transactions explicitly with ``BEGIN IMMEDIATE`` / ``COMMIT``.
* Every mutating operation is wrapped in a ``BEGIN IMMEDIATE`` transaction.
  IMMEDIATE takes the database write-lock up front, which serialises all
  writers. That gives us the atomicity required by NFR5 and prevents the
  read-then-write races that would otherwise allow double-spends or a transfer
  being reversed twice (BR8).
* Balances are never stored; they are always derived from ledger entries
  (BR6). See :mod:`app.ledger`.
"""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import CURRENCY, DB_PATH


def connect() -> sqlite3.Connection:
    """Open a new connection configured for this application."""
    conn = sqlite3.connect(
        DB_PATH,
        isolation_level=None,   # autocommit; we manage transactions ourselves
        timeout=30.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Run a block as a single atomic write transaction.

    Acquires the write-lock immediately, commits on success and rolls back on
    any exception, guaranteeing that a failure part-way through leaves no
    partial record (NFR5, BR4).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT    NOT NULL UNIQUE,
    password_hash  TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER UNIQUE,               -- NULL for the system account
    currency    TEXT    NOT NULL,
    is_system   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type                     TEXT    NOT NULL,   -- deposit|withdrawal|transfer|reversal
    status                   TEXT    NOT NULL,   -- completed|reversed
    created_at               TEXT    NOT NULL,
    reverses_transaction_id  INTEGER,            -- set only on reversals
    FOREIGN KEY (reverses_transaction_id) REFERENCES transactions (transaction_id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    ledger_entry_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id   INTEGER NOT NULL,
    account_id       INTEGER NOT NULL,
    amount_pence     INTEGER NOT NULL CHECK (amount_pence > 0),
    direction        TEXT    NOT NULL CHECK (direction IN ('debit', 'credit')),
    FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id),
    FOREIGN KEY (account_id)     REFERENCES accounts (account_id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_account   ON ledger_entries (account_id);
CREATE INDEX IF NOT EXISTS idx_ledger_txn       ON ledger_entries (transaction_id);
CREATE INDEX IF NOT EXISTS idx_txn_created_at   ON transactions   (created_at);
"""


def init_db() -> None:
    """Create the schema (if needed) and ensure the single system account exists."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        # BR5 / system account: one internal account, owned by no user.
        row = conn.execute(
            "SELECT account_id FROM accounts WHERE is_system = 1"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO accounts (user_id, currency, is_system) "
                "VALUES (NULL, ?, 1)",
                (CURRENCY,),
            )
    finally:
        conn.close()


def system_account_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT account_id FROM accounts WHERE is_system = 1"
    ).fetchone()
    if row is None:  # pragma: no cover - init_db guarantees this exists
        raise RuntimeError("System account is missing; database not initialised.")
    return int(row["account_id"])
