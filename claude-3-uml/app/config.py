"""Application configuration.

All monetary values are integer pence. Floating point is never used for money.
"""

import os

# --- Storage -----------------------------------------------------------------
# Path to the SQLite database file. Override with WALLET_DB_PATH.
DB_PATH: str = os.environ.get("WALLET_DB_PATH", "wallet.db")

# --- Currency ----------------------------------------------------------------
# The application supports GBP only.
CURRENCY: str = "GBP"

# --- Money -------------------------------------------------------------------
# Largest amount we accept in a single request, in pence. This bounds the
# "representable range" (SQLite stores 64-bit signed integers).
MAX_AMOUNT_PENCE: int = 2**63 - 1

# --- Business rules ----------------------------------------------------------
# BR3: combined value of all transfers and withdrawals in any rolling
# 24-hour window must not exceed GBP 1,000 (= 100,000 pence).
DAILY_LIMIT_PENCE: int = 100_000
DAILY_WINDOW_SECONDS: int = 24 * 60 * 60

# --- Authentication ----------------------------------------------------------
# Secret used to sign bearer tokens. MUST be overridden in production via the
# WALLET_SECRET environment variable.
SECRET_KEY: str = os.environ.get(
    "WALLET_SECRET", "dev-only-insecure-secret-change-me"
)
TOKEN_ALGORITHM: str = "HS256"
TOKEN_TTL_SECONDS: int = 24 * 60 * 60  # tokens are valid for 24 hours

# --- Password hashing (PBKDF2-HMAC-SHA256, standard library only) ------------
PBKDF2_ITERATIONS: int = 200_000
PBKDF2_SALT_BYTES: int = 16
