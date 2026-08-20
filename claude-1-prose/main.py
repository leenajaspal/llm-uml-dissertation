"""FastAPI application wiring and HTTP routes.

Run with:  uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse

import schemas
import services
from database import init_db
from dependencies import get_current_user
from errors import AppError


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Payments App", version="1.0.0", lifespan=lifespan)


@app.exception_handler(AppError)
async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


# --- auth --------------------------------------------------------------------


@app.post(
    "/auth/register",
    response_model=schemas.RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(body: schemas.RegisterRequest):
    return services.register_user(body.email, body.password)


@app.post("/auth/login", response_model=schemas.LoginResponse)
def login(body: schemas.LoginRequest):
    return services.login_user(body.email, body.password)


# --- account -----------------------------------------------------------------


@app.get("/accounts/me", response_model=schemas.AccountResponse)
def account_me(user: dict = Depends(get_current_user)):
    return services.get_account(user["id"])


# --- money movement ----------------------------------------------------------


@app.post(
    "/deposits",
    response_model=schemas.MoneyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_deposit(
    body: schemas.AmountRequest, user: dict = Depends(get_current_user)
):
    return services.deposit(user["id"], body.amount_pence)


@app.post(
    "/withdrawals",
    response_model=schemas.MoneyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_withdrawal(
    body: schemas.AmountRequest, user: dict = Depends(get_current_user)
):
    return services.withdraw(user["id"], body.amount_pence)


@app.post(
    "/transfers",
    response_model=schemas.MoneyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    body: schemas.TransferRequest, user: dict = Depends(get_current_user)
):
    return services.transfer(user["id"], body.recipient_email, body.amount_pence)


# --- history -----------------------------------------------------------------


@app.get("/transactions", response_model=list[schemas.TransactionItem])
def list_transactions(user: dict = Depends(get_current_user)):
    return services.list_transactions(user["id"])


# --- reversal ----------------------------------------------------------------


@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=schemas.ReversalResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse(transaction_id: int, user: dict = Depends(get_current_user)):
    return services.reverse_transaction(user["id"], transaction_id)
