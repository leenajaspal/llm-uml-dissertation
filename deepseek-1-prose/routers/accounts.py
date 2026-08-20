# routers/accounts.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from auth import get_current_user

router = APIRouter()

@router.get("/accounts/me", response_model=schemas.AccountResponse)
def get_account(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    account = db.query(models.Account).filter(models.Account.user_id == current_user.id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    return schemas.AccountResponse(
        account_id=account.id,
        balance_pence=account.balance_pence,
        currency=account.currency
    )