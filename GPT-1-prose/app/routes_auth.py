from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, status

from .database import get_db
from .schemas import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse
from .services import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict[str, object]:
    return register_user(conn, str(payload.email), payload.password)


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(payload: LoginRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict[str, str]:
    return authenticate_user(conn, str(payload.email), payload.password)
