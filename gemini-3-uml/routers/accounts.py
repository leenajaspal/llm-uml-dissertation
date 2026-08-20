from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import schemas, models, crud
from database import get_db
from security import get_current_user

router = APIRouter(tags=["accounts"])

@router.get("/accounts/me", response_model=schemas.AccountRes, status_code=200)
def get_account(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return {
        "account_id": user.account.account_id,
        "balance_pence": crud.get_balance(db, user.account.account_id),
        "currency": user.account.currency
    }
