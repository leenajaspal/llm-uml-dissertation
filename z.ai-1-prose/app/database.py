"""SQLite connection, schema initialisation and low-level helpers."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "payments.db"

_lock = threading.Lock()
_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Return the process-wide SQLite connection (single-writer model)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(
            DB_PATH,
            check_same_thread=False,
            isolation_level=None,          # manage transactions manually
            timeout=30.0,
        )
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA foreign_keys = ON")
        _connection.execute("PRAGMA journal_mode = WAL")
        _connection.execute("PRAGMA busy_timeout = 30000")
    return _connection


def init_db() -> None:
    conn = get_connection()
    with _lock:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL UNIQUE REFERENCES users(id),
                balance_pence INTEGER NOT NULL DEFAULT 0,
                currency      TEXT    NOT NULL DEFAULT 'GBP',
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id               INTEGER NOT NULL REFERENCES accounts(id),
                type                     TEXT    NOT NULL,
                direction                TEXT    NOT NULL,   -- 'incoming' | 'outgoing'
                amount_pence             INTEGER NOT NULL,
                status                   TEXT    NOT NULL,   -- 'completed' | 'reversed'
                reverses_transaction_id  INTEGER REFERENCES transactions(id),
                related_transaction_id   INTEGER REFERENCES transactions(id),
                created_at               TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_account
                ON transactions(account_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_transactions_reverses
                ON transactions(reverses_transaction_id);

            CREATE TABLE IF NOT EXISTS daily_totals (
                date            TEXT    NOT NULL,
                account_id      INTEGER NOT NULL REFERENCES accounts(id),
                total_out_pence INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (date, account_id)
            );
            """
        )


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Serialised write transaction. Rolls back on any exception."""
    conn = get_connection()
    with _lock:
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise