from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import schemas, models, crud
from database import get_db
from security import get_current_user

router = APIRouter(tags=["transactions"])

@router.post("/deposits", response_model=schemas.TxRes, status_code=201)
def deposit(req: schemas.AmountReq, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sys_acc = db.query(models.Account).filter(models.Account.user_id == None).first()
    
    tx = models.Transaction(type="deposit", status="completed")
    db.add(tx)
    db.flush()
    
    db.add(models.LedgerEntry(transaction_id=tx.transaction_id, account_id=sys_acc.account_id, amount_pence=req.amount_pence, direction="debit"))
    db.add(models.LedgerEntry(transaction_id=tx.transaction_id, account_id=user.account.account_id, amount_pence=req.amount_pence, direction="credit"))
    db.commit()
    
    return {"transaction_id": tx.transaction_id, "status": tx.status, "balance_pence": crud.get_balance(db, user.account.account_id)}

@router.post("/withdrawals", response_model=schemas.TxRes, status_code=201)
def withdraw(req: schemas.AmountReq, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sys_acc = db.query(models.Account).filter(models.Account.user_id == None).first()
    
    if crud.get_balance(db, user.account.account_id) < req.amount_pence:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    if not crud.check_24h_limit(db, user.account.account_id, req.amount_pence):
        raise HTTPException(status_code=400, detail="Rolling 24h limit exceeded")
        
    tx = models.Transaction(type="withdrawal", status="completed")
    db.add(tx)
    db.flush()
    
    db.add(models.LedgerEntry(transaction_id=tx.transaction_id, account_id=user.account.account_id, amount_pence=req.amount_pence, direction="debit"))
    db.add(models.LedgerEntry(transaction_id=tx.transaction_id, account_id=sys_acc.account_id, amount_pence=req.amount_pence, direction="credit"))
    db.commit()
    
    return {"transaction_id": tx.transaction_id, "status": tx.status, "balance_pence": crud.get_balance(db, user.account.account_id)}

@router.post("/transfers", response_model=schemas.TxRes, status_code=201)
def transfer(req: schemas.TransferReq, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if req.recipient_email == user.email:
        raise HTTPException(status_code=400, detail="Cannot transfer to own account")
        
    recipient = db.query(models.User).filter(models.User.email == req.recipient_email).first()
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient not found")
        
    if crud.get_balance(db, user.account.account_id) < req.amount_pence:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    if not crud.check_24h_limit(db, user.account.account_id, req.amount_pence):
        raise HTTPException(status_code=400, detail="Rolling 24h limit exceeded")
        
    tx = models.Transaction(type="transfer", status="completed")
    db.add(tx)
    db.flush()
    
    db.add(models.LedgerEntry(transaction_id=tx.transaction_id, account_id=user.account.account_id, amount_pence=req.amount_pence, direction="debit"))
    db.add(models.LedgerEntry(transaction_id=tx.transaction_id, account_id=recipient.account.account_id, amount_pence=req.amount_pence, direction="credit"))
    db.commit()
    
    return {"transaction_id": tx.transaction_id, "status": tx.status, "balance_pence": crud.get_balance(db, user.account.account_id)}

@router.get("/transactions", response_model=List[schemas.TransactionItem], status_code=200)
def get_transactions(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    results = db.query(models.Transaction, models.LedgerEntry).join(
        models.LedgerEntry, models.Transaction.transaction_id == models.LedgerEntry.transaction_id
    ).filter(models.LedgerEntry.account_id == user.account.account_id).order_by(models.Transaction.created_at.desc()).all()
    
    return [{
        "transaction_id": tx.transaction_id,
        "type": tx.type,
        "amount_pence": le.amount_pence,
        "direction": le.direction,
        "status": tx.status,
        "created_at": tx.created_at
    } for tx, le in results]

@router.post("/transactions/{transaction_id}/reversal", response_model=schemas.ReversalRes, status_code=201)
def reverse_transaction(transaction_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    orig_tx = db.query(models.Transaction).filter(models.Transaction.transaction_id == transaction_id).first()
    if not orig_tx or orig_tx.type != "transfer" or orig_tx.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed transfers can be reversed")
        
    sender_entry = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.transaction_id == orig_tx.transaction_id,
        models.LedgerEntry.account_id == user.account.account_id,
        models.LedgerEntry.direction == "debit"
    ).first()
    
    if not sender_entry:
        raise HTTPException(status_code=403, detail="Not authorized to reverse this transaction")
        
    if db.query(models.Transaction).filter(models.Transaction.reverses_transaction_id == orig_tx.transaction_id).first():
        raise HTTPException(status_code=400, detail="Transaction already reversed")
        
    rec_entry = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.transaction_id == orig_tx.transaction_id,
        models.LedgerEntry.direction == "credit"
    ).first()
    
    rev_tx = models.Transaction(type="reversal", status="completed", reverses_transaction_id=orig_tx.transaction_id)
    db.add(rev_tx)
    db.flush()
    
    db.add(models.LedgerEntry(transaction_id=rev_tx.transaction_id, account_id=sender_entry.account_id, amount_pence=sender_entry.amount_pence, direction="credit"))
    db.add(models.LedgerEntry(transaction_id=rev_tx.transaction_id, account_id=rec_entry.account_id, amount_pence=rec_entry.amount_pence, direction="debit"))
    
    orig_tx.status = "reversed"
    db.commit()
    
    return {
        "transaction_id": rev_tx.transaction_id,
        "reverses_transaction_id": orig_tx.transaction_id,
        "status": rev_tx.status
    }
