"""Password hashing and JWT helpers."""
from __future__ import annotations

import os
import time
from datetime import timedelta

import jwt
from passlib.context import CryptContext

JWT_ALGORITHM = "HS256"
JWT_TTL = timedelta(hours=24)

_jwt_secret = os.environ.get("JWT_SECRET", "dev-only-secret-change-me")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + int(JWT_TTL.total_seconds())}
    return jwt.encode(payload, _jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except Exception:
        return None