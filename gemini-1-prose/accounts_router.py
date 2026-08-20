from fastapi import APIRouter, Depends, HTTPException
import models, schemas, security
from database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.get("/me", response_model=schemas.AccountResponse)
def get_my_account(current_user: models.User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    account = db.query(models.Account).filter(models.Account.user_id == current_user.id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
        
    return {
        "account_id": account.id,
        "balance_pence": account.balance_pence,
        "currency": account.currency
    }