"""FastAPI application — route definitions and startup."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Path

from .database import init_db
from .deps import CurrentUser, get_current_user
from .errors import register_handlers
from .models import (
    AccountResponse,
    DepositRequest,
    LoginRequest,
    LoginResponse,
    MoneyMovementResponse,
    RegisterRequest,
    RegisterResponse,
    ReversalResponse,
    TransactionItem,
    TransferRequest,
    WithdrawalRequest,
)
from importlib import import_module

# Import service functions lazily to avoid circular import with security module.
services = import_module("app.services")


app = FastAPI(title="Payments Wallet API", version="1.0.0")
register_handlers(app)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --------------------------------------------------------------------- Auth
@app.post("/auth/register", response_model=RegisterResponse, status_code=201)
def register(body: RegisterRequest) -> RegisterResponse:
    user_id, email = services.register_user(body.email, body.password)
    return RegisterResponse(user_id=user_id, email=email)


@app.post("/auth/login", response_model=LoginResponse, status_code=200)
def login(body: LoginRequest) -> LoginResponse:
    token = services.authenticate(body.email, body.password)
    return LoginResponse(access_token=token)


# ------------------------------------------------------------------- Account
@app.get("/accounts/me", response_model=AccountResponse, status_code=200)
def my_account(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AccountResponse:
    data = services.get_account(user.account_id)
    return AccountResponse(**data)


# ------------------------------------------------------------- Money movement
@app.post("/deposits", response_model=MoneyMovementResponse, status_code=201)
def deposit(
    body: DepositRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MoneyMovementResponse:
    txn_id, balance = services.deposit(user.account_id, body.amount_pence)
    return MoneyMovementResponse(transaction_id=txn_id, status="completed", balance_pence=balance)


@app.post("/withdrawals", response_model=MoneyMovementResponse, status_code=201)
def withdraw(
    body: WithdrawalRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MoneyMovementResponse:
    txn_id, balance = services.withdraw(user.account_id, body.amount_pence)
    return MoneyMovementResponse(transaction_id=txn_id, status="completed", balance_pence=balance)


@app.post("/transfers", response_model=MoneyMovementResponse, status_code=201)
def transfer(
    body: TransferRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MoneyMovementResponse:
    txn_id, balance = services.transfer(
        user.account_id, user.email, body.recipient_email, body.amount_pence
    )
    return MoneyMovementResponse(transaction_id=txn_id, status="completed", balance_pence=balance)


# --------------------------------------------------------------- History
@app.get("/transactions", response_model=list[TransactionItem], status_code=200)
def list_transactions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[TransactionItem]:
    rows = services.list_transactions(user.account_id)
    return [TransactionItem(**r) for r in rows]


# --------------------------------------------------------------- Reversal
@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=201,
)
def reverse_transaction(
    transaction_id: Annotated[int, Path(gt=0)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReversalResponse:
    reversal_id, original_id, status = services.reverse_transaction(
        user.account_id, transaction_id
    )
    return ReversalResponse(
        transaction_id=reversal_id,
        reverses_transaction_id=original_id,
        status=status,
    )