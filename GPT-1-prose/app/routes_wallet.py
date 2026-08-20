from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, status

from .database import get_db
from .dependencies import get_current_user
from .schemas import (
    AccountResponse,
    AmountRequest,
    DepositWithdrawalResponse,
    ReversalResponse,
    TransactionResponse,
    TransferRequest,
    TransferResponse,
)
from .services import (
    account_response,
    create_deposit,
    create_transfer,
    create_withdrawal,
    list_user_transactions,
    reverse_transaction,
)

router = APIRouter(tags=["wallet"])


@router.get("/accounts/me", response_model=AccountResponse, status_code=status.HTTP_200_OK)
def get_my_account(
    current_user: dict[str, object] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, object]:
    return account_response(conn, int(current_user["id"]))


@router.post("/deposits", response_model=DepositWithdrawalResponse, status_code=status.HTTP_201_CREATED)
def deposit(
    payload: AmountRequest,
    current_user: dict[str, object] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, object]:
    return create_deposit(conn, int(current_user["id"]), payload.amount_pence)


@router.post("/withdrawals", response_model=DepositWithdrawalResponse, status_code=status.HTTP_201_CREATED)
def withdrawal(
    payload: AmountRequest,
    current_user: dict[str, object] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, object]:
    return create_withdrawal(conn, int(current_user["id"]), payload.amount_pence)


@router.post("/transfers", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def transfer(
    payload: TransferRequest,
    current_user: dict[str, object] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, object]:
    return create_transfer(conn, int(current_user["id"]), str(payload.recipient_email), payload.amount_pence)


@router.get("/transactions", response_model=list[TransactionResponse], status_code=status.HTTP_200_OK)
def transactions(
    current_user: dict[str, object] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict[str, object]]:
    return list_user_transactions(conn, int(current_user["id"]))


@router.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=status.HTTP_201_CREATED,
)
def reversal(
    transaction_id: str,
    current_user: dict[str, object] = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, object]:
    return reverse_transaction(conn, int(current_user["id"]), transaction_id)
