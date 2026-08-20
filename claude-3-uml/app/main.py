"""FastAPI application wiring for the payments wallet.

Endpoint paths, request field names and response field names follow the
required contract exactly. Success codes: 201 for register / money-movements /
reversal, 200 for login / account / history.

Error handling (not covered by the contract, chosen here):
* 422 - request body fails validation, or a business rule rejects the amount
        (insufficient funds, daily limit, self-transfer). No account changes.
* 401 - missing / invalid / expired token, or bad login credentials.
* 403 - authenticated, but acting on a transfer you did not send.
* 404 - unknown recipient, or a transaction you cannot see / does not exist.
* 409 - registering an existing email, or reversing something not reversible.
"""

import sqlite3
from contextlib import asynccontextmanager
from typing import Iterator

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import ledger
from .config import CURRENCY
from .db import connect, init_db, write_transaction
from .ledger import WalletError
from .schemas import (
    AccountResponse,
    AmountRequest,
    LoginRequest,
    LoginResponse,
    MovementResponse,
    RegisterRequest,
    RegisterResponse,
    ReversalResponse,
    TransactionList,
    TransferRequest,
)
from .security import (
    create_access_token,
    decode_access_token,
    hash_password,
    now_iso,
    verify_password,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Payments Wallet", version="1.0.0", lifespan=lifespan)

_bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    conn: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    """Resolve the authenticated user from the bearer token (NFR2)."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise WalletError(401, "authentication required")
    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError:
        raise WalletError(401, "invalid or expired token")

    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if user is None:
        raise WalletError(401, "invalid or expired token")
    return user


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
@app.exception_handler(WalletError)
async def wallet_error_handler(request: Request, exc: WalletError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# --------------------------------------------------------------------------- #
# Auth (public)
# --------------------------------------------------------------------------- #
@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    body: RegisterRequest, conn: sqlite3.Connection = Depends(get_db)
) -> RegisterResponse:
    """FR1: create one user and one account."""
    email = body.email.lower()
    password_hash = hash_password(body.password)
    try:
        with write_transaction(conn):
            existing = conn.execute(
                "SELECT 1 FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing is not None:
                raise WalletError(409, "email already registered")
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) "
                "VALUES (?, ?, ?)",
                (email, password_hash, now_iso()),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO accounts (user_id, currency, is_system) "
                "VALUES (?, ?, 0)",
                (user_id, CURRENCY),
            )
    except sqlite3.IntegrityError:
        # Backstop for a concurrent registration of the same email.
        raise WalletError(409, "email already registered")

    return RegisterResponse(user_id=user_id, email=email)


@app.post("/auth/login", response_model=LoginResponse)
def login(
    body: LoginRequest, conn: sqlite3.Connection = Depends(get_db)
) -> LoginResponse:
    """FR2: authenticate and issue a bearer token."""
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (body.email.lower(),)
    ).fetchone()
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise WalletError(401, "invalid email or password")
    token = create_access_token(int(user["user_id"]))
    return LoginResponse(access_token=token)


# --------------------------------------------------------------------------- #
# Account
# --------------------------------------------------------------------------- #
@app.get("/accounts/me", response_model=AccountResponse)
def get_my_account(
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> AccountResponse:
    """FR3: the caller's own balance, derived from the ledger."""
    account_id = ledger.user_account_id(conn, int(user["user_id"]))
    balance = ledger.account_balance(conn, account_id)
    return AccountResponse(
        account_id=account_id, balance_pence=balance, currency=CURRENCY
    )


# --------------------------------------------------------------------------- #
# Money movements
# --------------------------------------------------------------------------- #
@app.post(
    "/deposits",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_deposit(
    body: AmountRequest,
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> MovementResponse:
    result = ledger.deposit(conn, int(user["user_id"]), body.amount_pence)
    return MovementResponse(**result)


@app.post(
    "/withdrawals",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_withdrawal(
    body: AmountRequest,
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> MovementResponse:
    result = ledger.withdraw(conn, int(user["user_id"]), body.amount_pence)
    return MovementResponse(**result)


@app.post(
    "/transfers",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    body: TransferRequest,
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> MovementResponse:
    result = ledger.transfer(
        conn, int(user["user_id"]), body.recipient_email, body.amount_pence
    )
    return MovementResponse(**result)


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
@app.get("/transactions", response_model=TransactionList)
def get_transactions(
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> TransactionList:
    """FR7: the caller's own transaction history."""
    return ledger.list_transactions(conn, int(user["user_id"]))


@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reversal(
    transaction_id: int,
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> ReversalResponse:
    """FR8: reverse a completed transfer the caller sent."""
    result = ledger.reverse_transfer(conn, int(user["user_id"]), transaction_id)
    return ReversalResponse(**result)


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
