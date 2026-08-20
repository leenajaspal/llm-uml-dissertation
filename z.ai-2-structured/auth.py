"""Authentication utilities: password hashing (PBKDF2) and JWT (HMAC-SHA256).

Implemented with the standard library only, to minimise external dependencies.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

# In production these would come from configuration/secrets management.
SECRET_KEY = os.environ.get("WALLET_SECRET_KEY", "dev-secret-please-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_SECONDS = 24 * 3600
PBKDF2_ITERATIONS = 200_000


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str, salt: Optional[str] = None) -> tuple:
    """Return (hash_hex, salt_hex). Generates a fresh per-user salt if none given."""
    if salt is None:
        salt = os.urandom(16).hex()
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    )
    return derived.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    computed, _ = hash_password(password, salt)
    return hmac.compare_digest(computed, stored_hash)


def create_access_token(user_id: int) -> str:
    now = int(time.time())
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_EXPIRE_SECONDS}
    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    sig = hmac.new(
        SECRET_KEY.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64encode(sig)}"


def decode_access_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64encode(expected_sig), sig_b64):
            return None
        payload = json.loads(_b64decode(payload_b64))
        if not isinstance(payload, dict):
            return None
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None