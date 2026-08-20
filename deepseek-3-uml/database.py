import sqlite3
from contextlib import contextmanager
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "wallet.db")

def get_db_connection():
    """Create a database connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initialize the database schema."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                currency TEXT DEFAULT 'GBP',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- System account (not owned by any user)
            INSERT OR IGNORE INTO users (user_id, email, password_hash)
            VALUES (0, 'system@internal', 'SYSTEM_ACCOUNT_NO_LOGIN');
            
            INSERT OR IGNORE INTO accounts (account_id, user_id, currency)
            VALUES (0, 0, 'GBP');

            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('deposit', 'withdrawal', 'transfer', 'reversal')),
                status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('completed', 'reversed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reverses_transaction_id INTEGER,
                FOREIGN KEY (reverses_transaction_id) REFERENCES transactions(transaction_id)
            );

            CREATE TABLE IF NOT EXISTS ledger_entries (
                ledger_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                amount_pence INTEGER NOT NULL CHECK(amount_pence > 0),
                direction TEXT NOT NULL CHECK(direction IN ('debit', 'credit')),
                FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
                FOREIGN KEY (account_id) REFERENCES accounts(account_id)
            );

            CREATE INDEX IF NOT EXISTS idx_ledger_account ON ledger_entries(account_id);
            CREATE INDEX IF NOT EXISTS idx_ledger_transaction ON ledger_entries(transaction_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_type_status ON transactions(type, status);
        """)