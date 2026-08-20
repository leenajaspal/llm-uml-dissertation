from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_account, get_current_user
from schemas import TransactionResponse, ReversalResponse
from models import Account, User
from services.transaction_service import get_transaction_history, reverse_transfer

router = APIRouter()

@router.get("/transactions", response_model=list[TransactionResponse], status_code=200)
def get_transactions(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    return get_transaction_history(db, account)

@router.post("/transactions/{transaction_id}/reversal", response_model=ReversalResponse, status_code=201)
def create_reversal(
    transaction_id: int,
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    try:
        reversal_txn = reverse_transfer(db, transaction_id, user.id)
        return ReversalResponse(
            transaction_id=reversal_txn.id,
            reverses_transaction_id=transaction_id,
            status=reversal_txn.status.value
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )