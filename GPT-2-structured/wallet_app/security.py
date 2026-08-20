"""Password and bearer-token helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .config import ACCESS_TOKEN_TTL_HOURS, PASSWORD_HASH_ITERATIONS


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def iso_from_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def token_expiry_iso() -> str:
    return iso_from_datetime(now_utc() + timedelta(hours=ACCESS_TOKEN_TTL_HOURS))


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(32)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return salt.hex(), password_hash.hex()


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return hmac.compare_digest(actual_hash, expected_hash_hex)


def create_access_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
