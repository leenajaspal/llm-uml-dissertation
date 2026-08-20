from sqlalchemy import func
from datetime import datetime, timedelta, timezone
import models

def get_balance(db, account_id: str) -> int:
    credits = db.query(func.sum(models.LedgerEntry.amount_pence)).filter(
        models.LedgerEntry.account_id == account_id,
        models.LedgerEntry.direction == "credit"
    ).scalar() or 0
    debits = db.query(func.sum(models.LedgerEntry.amount_pence)).filter(
        models.LedgerEntry.account_id == account_id,
        models.LedgerEntry.direction == "debit"
    ).scalar() or 0
    return credits - debits

def check_24h_limit(db, account_id: str, amount_pence: int) -> bool:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    debits = db.query(func.sum(models.LedgerEntry.amount_pence)).join(models.Transaction).filter(
        models.LedgerEntry.account_id == account_id,
        models.LedgerEntry.direction == "debit",
        models.Transaction.type.in_(["withdrawal", "transfer"]),
        models.Transaction.created_at >= since
    ).scalar() or 0
    
    return (debits + amount_pence) <= 100000
