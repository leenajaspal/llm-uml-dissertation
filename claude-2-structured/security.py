"""Password hashing (PBKDF2-HMAC-SHA256) and JWT access tokens.

Only widely available libraries are used: hashlib/hmac/os from the standard
library for password storage, and PyJWT for tokens.
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    PBKDF2_ITERATIONS,
    SECRET_KEY,
)


def hash_password(password: str) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) for a plaintext password.

    A fresh 16-byte salt is generated per user (NFR1). The derived key is a
    one-way PBKDF2-HMAC-SHA256 hash; the plaintext cannot be recovered.
    """
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), derived.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Constant-time verification of a password against stored salt+hash."""
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(derived.hex(), hash_hex)


def create_access_token(user_id: int) -> str:
    """Issue a signed JWT bearer token for the given user id."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.PyJWTError if invalid/expired."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
