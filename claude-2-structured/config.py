"""Application configuration.

All monetary values are integer pence. Floating point is never used for money.
"""
import os

# --- Security / auth ---------------------------------------------------------
# In production this MUST be supplied via the environment. The default exists
# only so the app can run out of the box for evaluation.
SECRET_KEY = os.environ.get("WALLET_SECRET_KEY", "dev-only-secret-change-me-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
PBKDF2_ITERATIONS = 200_000

# --- Domain ------------------------------------------------------------------
CURRENCY = "GBP"  # the application supports GBP only

# BR3: combined transfers + withdrawals may not exceed £1,000 in any rolling
# 24-hour window (measured backwards from the moment of the request).
DAILY_LIMIT_PENCE = 100_000  # £1,000.00
DAILY_WINDOW_HOURS = 24

# NFR4 / BR11: amounts must be positive whole pence within the representable
# range. SQLite stores signed 64-bit integers.
MAX_AMOUNT_PENCE = 2 ** 63 - 1

# --- Storage -----------------------------------------------------------------
DATABASE_URL = os.environ.get("WALLET_DATABASE_URL", "sqlite:///./wallet.db")
