from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import HTTPException, status

from .config import settings

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "${}".format("$".join([
        PASSWORD_ALGORITHM,
        str(PASSWORD_ITERATIONS),
        _b64url_encode(salt),
        _b64url_encode(digest),
    ]))


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    try:
        _, algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 4)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64url_decode(salt_text)
        expected = _b64url_decode(digest_text)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def create_access_token(user_id: int) -> str:
    """Create a compact HMAC-signed bearer token."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + settings.ACCESS_TOKEN_TTL_SECONDS,
    }
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> int:
    """Validate a bearer token and return the user id in its subject."""
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise invalid_exc
        payload: dict[str, Any] = json.loads(_b64url_decode(encoded_payload))
        if int(payload["exp"]) < int(time.time()):
            raise invalid_exc
        return int(payload["sub"])
    except HTTPException:
        raise
    except Exception:
        raise invalid_exc
