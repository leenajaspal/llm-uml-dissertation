"""Application configuration constants."""

from __future__ import annotations

import os


DATABASE_URL = os.getenv("WALLET_DATABASE_URL", "wallet.sqlite3")
SYSTEM_ACCOUNT_ID = "system"
CURRENCY = "GBP"
ROLLING_LIMIT_PENCE = 100_000  # £1,000.00
ROLLING_LIMIT_HOURS = 24
MAX_AMOUNT_PENCE = 9_000_000_000_000  # safely below SQLite signed 64-bit limits
PASSWORD_HASH_ITERATIONS = 600_000
ACCESS_TOKEN_TTL_HOURS = 24 * 7
