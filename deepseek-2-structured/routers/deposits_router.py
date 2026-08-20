from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_account
from schemas import AmountRequest, OperationResponse
from models import Account
from services.transaction_service import process_deposit

router = APIRouter()

@router.post("/deposits", response_model=OperationResponse, status_code=201)
def create_deposit(
    request: AmountRequest,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    transaction, balance = process_deposit(db, account, request.amount_pence)
    return OperationResponse(
        transaction_id=transaction.id,
        status=transaction.status.value,
        balance_pence=balance
    )