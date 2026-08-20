from fastapi import APIRouter, Depends
from dependencies import get_current_account
from schemas import AccountResponse
from services.account_service import get_account_balance
from models import Account

router = APIRouter()

@router.get("/accounts/me", response_model=AccountResponse, status_code=200)
def get_my_account(account: Account = Depends(get_current_account)):
    balance = get_account_balance(account)
    return AccountResponse(
        account_id=account.id,
        balance_pence=balance,
        currency=account.currency
    )