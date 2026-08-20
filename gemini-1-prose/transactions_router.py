from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import List
import models, schemas, security
from database import get_db

router = APIRouter(tags=["transactions"])

DAILY_LIMIT_PENCE = 100000  # £1000

def get_user_account(db: Session, user_id: int):
    return db.query(models.Account).filter(models.Account.user_id == user_id).first()

def check_daily_limit(db: Session, account_id: int, amount: int):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    outflows = db.query(func.sum(models.Transaction.amount_pence)).filter(
        models.Transaction.account_id == account_id,
        models.Transaction.direction == "DEBIT",
        models.Transaction.status == "COMPLETED",
        models.Transaction.created_at >= today
    ).scalar() or 0
    
    if outflows + amount > DAILY_LIMIT_PENCE:
        raise HTTPException(status_code=400, detail="Daily withdrawal/transfer limit of £1000 exceeded")

@router.post("/deposits", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_deposit(request: schemas.AmountRequest, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    if request.amount_pence <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
        
    account = db.query(models.Account).filter(models.Account.user_id == current_user.id).with_for_update().first()
    account.balance_pence += request.amount_pence
    
    tx = models.Transaction(
        account_id=account.id, type="DEPOSIT", amount_pence=request.amount_pence,
        direction="CREDIT", status="COMPLETED"
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    
    return {"transaction_id": tx.id, "status": tx.status, "balance_pence": account.balance_pence}

@router.post("/withdrawals", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_withdrawal(request: schemas.AmountRequest, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    if request.amount_pence <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
        
    account = db.query(models.Account).filter(models.Account.user_id == current_user.id).with_for_update().first()
    
    if account.balance_pence < request.amount_pence:
        raise HTTPException(status_code=400, detail="Insufficient funds")
        
    check_daily_limit(db, account.id, request.amount_pence)
    account.balance_pence -= request.amount_pence
    
    tx = models.Transaction(
        account_id=account.id, type="WITHDRAWAL", amount_pence=request.amount_pence,
        direction="DEBIT", status="COMPLETED"
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    
    return {"transaction_id": tx.id, "status": tx.status, "balance_pence": account.balance_pence}

@router.post("/transfers", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(request: schemas.TransferRequest, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    if request.amount_pence <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if request.recipient_email == current_user.email:
        raise HTTPException(status_code=400, detail="Cannot transfer to yourself")
        
    recipient = db.query(models.User).filter(models.User.email == request.recipient_email).first()
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient not found")
        
    sender_account = get_user_account(db, current_user.id)
    recipient_account = get_user_account(db, recipient.id)
    
    # Deadlock prevention: consistently lock by ascending ID order
    if sender_account.id < recipient_account.id:
        db.query(models.Account).filter(models.Account.id == sender_account.id).with_for_update().first()
        db.query(models.Account).filter(models.Account.id == recipient_account.id).with_for_update().first()
    else:
        db.query(models.Account).filter(models.Account.id == recipient_account.id).with_for_update().first()
        db.query(models.Account).filter(models.Account.id == sender_account.id).with_for_update().first()
        
    if sender_account.balance_pence < request.amount_pence:
        raise HTTPException(status_code=400, detail="Insufficient funds")
        
    check_daily_limit(db, sender_account.id, request.amount_pence)
    
    sender_account.balance_pence -= request.amount_pence
    recipient_account.balance_pence += request.amount_pence
    
    tx_out = models.Transaction(account_id=sender_account.id, type="TRANSFER", amount_pence=request.amount_pence, direction="DEBIT", status="COMPLETED")
    tx_in = models.Transaction(account_id=recipient_account.id, type="TRANSFER", amount_pence=request.amount_pence, direction="CREDIT", status="COMPLETED")
    
    db.add_all([tx_out, tx_in])
    db.flush()
    
    tx_out.related_transaction_id = tx_in.id
    tx_in.related_transaction_id = tx_out.id
    db.commit()
    
    return {"transaction_id": tx_out.id, "status": tx_out.status, "balance_pence": sender_account.balance_pence}

@router.get("/transactions", response_model=List[schemas.TransactionHistoryItem])
def get_transactions(current_user: models.User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    account = get_user_account(db, current_user.id)
    transactions = db.query(models.Transaction).filter(models.Transaction.account_id == account.id).order_by(models.Transaction.created_at.desc()).all()
    return transactions

@router.post("/transactions/{transaction_id}/reversal", response_model=schemas.ReversalResponse, status_code=status.HTTP_201_CREATED)
def reverse_transaction(transaction_id: int, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(get_db)):
    account = get_user_account(db, current_user.id)
    original_tx = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id, 
        models.Transaction.account_id == account.id
    ).first()
    
    if not original_tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if original_tx.status == "REVERSED":
        raise HTTPException(status_code=400, detail="Transaction already reversed")
        
    if original_tx.type == "TRANSFER":
        related_tx = db.query(models.Transaction).filter(models.Transaction.id == original_tx.related_transaction_id).first()
        
        sender_acc_id = original_tx.account_id if original_tx.direction == "DEBIT" else related_tx.account_id
        recipient_acc_id = related_tx.account_id if original_tx.direction == "DEBIT" else original_tx.account_id
        
        # Deadlock prevention
        if sender_acc_id < recipient_acc_id:
            db.query(models.Account).filter(models.Account.id == sender_acc_id).with_for_update().first()
            db.query(models.Account).filter(models.Account.id == recipient_acc_id).with_for_update().first()
        else:
            db.query(models.Account).filter(models.Account.id == recipient_acc_id).with_for_update().first()
            db.query(models.Account).filter(models.Account.id == sender_acc_id).with_for_update().first()
            
        sender_account = db.query(models.Account).filter(models.Account.id == sender_acc_id).first()
        recipient_account = db.query(models.Account).filter(models.Account.id == recipient_acc_id).first()
        
        if recipient_account.balance_pence < original_tx.amount_pence:
            raise HTTPException(status_code=400, detail="Recipient has insufficient funds for reversal")
            
        recipient_account.balance_pence -= original_tx.amount_pence
        sender_account.balance_pence += original_tx.amount_pence
        
        rev_out = models.Transaction(account_id=recipient_account.id, type="TRANSFER", amount_pence=original_tx.amount_pence, direction="DEBIT", status="COMPLETED", reverses_transaction_id=related_tx.id if original_tx.direction == "DEBIT" else original_tx.id)
        rev_in = models.Transaction(account_id=sender_account.id, type="TRANSFER", amount_pence=original_tx.amount_pence, direction="CREDIT", status="COMPLETED", reverses_transaction_id=original_tx.id if original_tx.direction == "DEBIT" else related_tx.id)
        
        original_tx.status = "REVERSED"
        related_tx.status = "REVERSED"
        
        db.add_all([rev_out, rev_in])
        db.flush()
        
        rev_out.related_transaction_id = rev_in.id
        rev_in.related_transaction_id = rev_out.id
        db.commit()
        
        reversal_id = rev_in.id if original_tx.direction == "DEBIT" else rev_out.id
        
    else:
        db.query(models.Account).filter(models.Account.id == account.id).with_for_update().first()
        
        if original_tx.direction == "CREDIT": # Reversing deposit
            if account.balance_pence < original_tx.amount_pence:
                raise HTTPException(status_code=400, detail="Insufficient funds for reversal")
            account.balance_pence -= original_tx.amount_pence
            new_dir = "DEBIT"
        else: # Reversing withdrawal
            account.balance_pence += original_tx.amount_pence
            new_dir = "CREDIT"
            
        rev_tx = models.Transaction(
            account_id=account.id, type=original_tx.type, amount_pence=original_tx.amount_pence,
            direction=new_dir, status="COMPLETED", reverses_transaction_id=original_tx.id
        )
        original_tx.status = "REVERSED"
        db.add(rev_tx)
        db.commit()
        db.refresh(rev_tx)
        reversal_id = rev_tx.id
        
    return {"transaction_id": reversal_id, "reverses_transaction_id": original_tx.id, "status": "COMPLETED"}