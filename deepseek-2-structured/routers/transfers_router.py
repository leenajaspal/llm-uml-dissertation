from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_account
from schemas import TransferRequest, OperationResponse
from models import Account
from services.transaction_service import process_transfer

router = APIRouter()

@router.post("/transfers", response_model=OperationResponse, status_code=201)
def create_transfer(
    request: TransferRequest,
    sender_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    try:
        transaction, balance = process_transfer(
            db, sender_account, request.recipient_email, request.amount_pence
        )
        return OperationResponse(
            transaction_id=transaction.id,
            status=transaction.status.value,
            balance_pence=balance
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )