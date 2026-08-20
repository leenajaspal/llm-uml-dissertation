import sqlite3
from fastapi import APIRouter, Depends

from dependencies import get_current_user, get_db
from schemas import AccountResponse
from services import compute_balance, get_user_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=AccountResponse, status_code=200)
def get_my_account(
    user_id: int = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    acc = get_user_account(conn, user_id)
    balance = compute_balance(conn, int(acc["account_id"]))
    return AccountResponse(
        account_id=int(acc["account_id"]),
        balance_pence=balance,
        currency=acc["currency"],
    )