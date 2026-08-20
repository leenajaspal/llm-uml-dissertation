"""FastAPI dependencies — current-user resolution from the bearer token."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_connection
from .errors import AuthError, NotFoundError
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    __slots__ = ("user_id", "email", "account_id", "currency")

    def __init__(self, user_id: int, email: str, account_id: int, currency: str):
        self.user_id = user_id
        self.email = email
        self.account_id = account_id
        self.currency = currency


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthError("missing or invalid Authorization header")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise AuthError("invalid or expired token")

    conn = get_connection()
    row = conn.execute(
        """
        SELECT u.id AS user_id, u.email, a.id AS account_id, a.currency
        FROM users u JOIN accounts a ON a.user_id = u.id
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError("user not found")
    return CurrentUser(
        user_id=row["user_id"],
        email=row["email"],
        account_id=row["account_id"],
        currency=row["currency"],
    )