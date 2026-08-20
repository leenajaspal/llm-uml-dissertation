from datetime import datetime, timezone

import sqlite3
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_db
from schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from security import generate_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(req: RegisterRequest, conn: sqlite3.Connection = Depends(get_db)):
    email = req.email.strip().lower()
    existing = conn.execute(
        "SELECT user_id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    salt, password_hash = hash_password(req.password)
    now = datetime.now(timezone.utc).isoformat()

    user_cur = conn.execute(
        "INSERT INTO users (email, password_hash, password_salt, created_at) "
        "VALUES (?,?,?,?)",
        (email, password_hash, salt, now),
    )
    user_id = int(user_cur.lastrowid)
    conn.execute(
        "INSERT INTO accounts (user_id, currency, is_system) VALUES (?, 'GBP', 0)",
        (user_id,),
    )
    return RegisterResponse(user_id=user_id, email=email)


@router.post("/login", response_model=LoginResponse, status_code=200)
def login(req: LoginRequest, conn: sqlite3.Connection = Depends(get_db)):
    email = req.email.strip().lower()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    if row is None or not verify_password(
        req.password, row["password_salt"], row["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = generate_token()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, created_at) VALUES (?,?,?)",
        (token, int(row["user_id"]), now),
    )
    return LoginResponse(access_token=token)