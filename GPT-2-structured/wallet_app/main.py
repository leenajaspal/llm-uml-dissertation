"""FastAPI application exposing the peer-to-peer wallet API."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import services
from .database import get_db, init_db
from .schemas import (
    AccountResponse,
    AmountRequest,
    LoginRequest,
    LoginResponse,
    MoneyMovementResponse,
    RegisterRequest,
    RegisterResponse,
    ReversalResponse,
    TransactionHistoryItem,
    TransferRequest,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="Peer-to-peer payments wallet",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

bearer_scheme = HTTPBearer(auto_error=False)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> sqlite3.Row:
    token = credentials.credentials if credentials else None
    return services.current_user_from_token(db, token)


@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, str]:
    return services.register_user(db, request.email, request.password)


@app.post("/auth/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(
    request: LoginRequest,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, str]:
    return services.login(db, request.email, request.password)


@app.get("/accounts/me", response_model=AccountResponse, status_code=status.HTTP_200_OK)
def get_account_me(
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, object]:
    return services.get_my_account(db, user["id"])


@app.post(
    "/deposits",
    response_model=MoneyMovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_deposit(
    request: AmountRequest,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, object]:
    return services.deposit(db, user["id"], request.amount_pence)


@app.post(
    "/withdrawals",
    response_model=MoneyMovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_withdrawal(
    request: AmountRequest,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, object]:
    return services.withdraw(db, user["id"], request.amount_pence)


@app.post(
    "/transfers",
    response_model=MoneyMovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    request: TransferRequest,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, object]:
    return services.transfer(
        db,
        user_id=user["id"],
        sender_email=user["email"],
        recipient_email=request.recipient_email,
        amount_pence=request.amount_pence,
    )


@app.get(
    "/transactions",
    response_model=list[TransactionHistoryItem],
    status_code=status.HTTP_200_OK,
)
def get_transactions(
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> list[dict[str, object]]:
    return services.transactions_for_user(db, user["id"])


@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_transaction(
    transaction_id: str,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, str]:
    return services.reverse_transfer(db, user["id"], transaction_id)
