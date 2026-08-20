import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AuthToken, User


PASSWORD_ITERATIONS = 390_000
TOKEN_BYTES = 32

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    if salt_hex is None:
        salt = secrets.token_bytes(16)
        salt_hex = salt.hex()
    else:
        salt = bytes.fromhex(salt_hex)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return digest.hex(), salt_hex


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    actual_hash, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(actual_hash, expected_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_access_token(db: Session, user: User) -> str:
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(AuthToken(token_hash=hash_token(raw_token), user_id=user.user_id))
    return raw_token


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hash_token(credentials.credentials)
    auth_token = db.get(AuthToken, token_hash)
    if auth_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, auth_token.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
