from typing import Iterator, Optional

import sqlite3
from fastapi import Depends, Header, HTTPException

from db import get_connection


def get_db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
        )
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
        )
    row = conn.execute(
        "SELECT user_id FROM auth_tokens WHERE token = ?", (token,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return int(row["user_id"])