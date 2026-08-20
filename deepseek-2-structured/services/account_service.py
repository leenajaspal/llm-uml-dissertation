from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import Account, LedgerEntry, Direction
from database import SessionLocal

def get_account_balance(account: Account) -> int:
    credits = sum(
        entry.amount_pence for entry in account.ledger_entries 
        if entry.direction == Direction.CREDIT
    )
    debits = sum(
        entry.amount_pence for entry in account.ledger_entries 
        if entry.direction == Direction.DEBIT
    )
    return credits - debits

def create_system_account():
    db = SessionLocal()
    try:
        existing = db.query(Account).filter(Account.is_system == 1).first()
        if not existing:
            system_account = Account(is_system=1, currency="GBP")
            db.add(system_account)
            db.commit()
    finally:
        db.close()

def get_system_account(db: Session) -> Account:
    return db.query(Account).filter(Account.is_system == 1).first()