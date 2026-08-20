import hashlib
import hmac
import secrets
from typing import Optional, Tuple

_PBKDF2_ITERATIONS = 200_000
_HASH_NAME = "sha256"


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Return (salt, password_hash). Salt is hex; hash is hex digest."""
    if salt is None:
        salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        _HASH_NAME,
        password.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return salt, derived.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, computed = hash_password(password, salt)
    return hmac.compare_digest(computed, expected_hash)


def generate_token() -> str:
    return secrets.token_urlsafe(32)