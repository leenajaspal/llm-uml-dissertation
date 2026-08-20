"""FastAPI dependencies."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import read_connection
from errors import AuthError
from security import decode_token

# auto_error=False so we can return a 401 (with WWW-Authenticate) for a missing
# credential rather than the library's default 403.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise AuthError("Missing authentication credentials")

    user_id = decode_token(credentials.credentials)

    with read_connection() as conn:
        user = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    if user is None:
        raise AuthError("Invalid authentication credentials")

    return {"id": user["id"], "email": user["email"]}
