"""Shared FastAPI dependencies."""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User
from security import decode_access_token

# auto_error=False so we can return a 401 (rather than 403) with a clear
# message when the Authorization header is missing or malformed.
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)
_INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token (NFR2).

    A user only ever acts on their own account; every account/transaction
    lookup downstream is scoped to this user, so an identifier belonging to
    another user cannot grant access (NFR3).
    """
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise _UNAUTHENTICATED

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise _INVALID_TOKEN

    user = db.get(User, user_id)
    if user is None:
        raise _INVALID_TOKEN
    return user
