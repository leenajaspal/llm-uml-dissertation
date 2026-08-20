"""Application configuration and constants.

All monetary values across the application are integers representing pence.
"""
import os
import secrets
from pathlib import Path

# --- Storage -----------------------------------------------------------------
DB_PATH = os.environ.get("PAYMENTS_DB_PATH", "payments.db")

# --- Business rules ----------------------------------------------------------
CURRENCY = "GBP"

# Daily cap on how much money a single user may move *out* of their account
# (withdrawals + transfers sent) within one UTC calendar day. £1000 = 100000p.
# The cap exists to limit damage from account takeover, so only outgoing money
# counts; deposits, received transfers and reversals do not.
DAILY_LIMIT_PENCE = 100_000

# Guard rail on any single amount to keep values sane (£1,000,000).
MAX_TXN_PENCE = 100_000_000

# --- Auth --------------------------------------------------------------------
JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _load_secret_key() -> str:
    """Load the JWT signing secret.

    Order of preference:
      1. PAYMENTS_SECRET_KEY environment variable.
      2. A persisted key file (so tokens survive restarts).
      3. A freshly generated key, persisted to the key file.
    """
    env_key = os.environ.get("PAYMENTS_SECRET_KEY")
    if env_key:
        return env_key

    key_file = Path(os.environ.get("PAYMENTS_SECRET_FILE", ".payments_secret"))
    if key_file.exists():
        content = key_file.read_text().strip()
        if content:
            return content

    generated = secrets.token_urlsafe(48)
    try:
        key_file.write_text(generated)
        os.chmod(key_file, 0o600)
    except OSError:
        # If we cannot persist it we still run; tokens simply won't survive a
        # restart. This never blocks the app from starting.
        pass
    return generated


SECRET_KEY = _load_secret_key()
