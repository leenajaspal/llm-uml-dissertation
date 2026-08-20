"""Password hashing and bearer-token handling.

NFR1: passwords are stored using a one-way hash (PBKDF2-HMAC-SHA256) with a
per-user random salt. The plaintext password is never stored, never logged and
never returned in any response.
"""

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone

import jwt  # PyJWT

from .config import (
    PBKDF2_ITERATIONS,
    PBKDF2_SALT_BYTES,
    SECRET_KEY,
    TOKEN_ALGORITHM,
    TOKEN_TTL_SECONDS,
)


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Return a self-describing hash string: ``pbkdf2_sha256$iters$salt$hash``."""
    salt = os.urandom(PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS, salt.hex(), derived.hex()
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    try:
        algorithm, iterations_s, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(derived, expected)


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def create_access_token(user_id: int) -> str:
    """Issue a signed bearer token identifying the user."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=TOKEN_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Return the user_id encoded in a valid token.

    Raises ``ValueError`` if the token is missing, malformed, expired or has a
    bad signature.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise ValueError("invalid or expired token") from exc


# --------------------------------------------------------------------------- #
# Timestamps
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    """Current UTC time as a sortable ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
