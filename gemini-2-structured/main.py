from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import models, schemas, auth, database
from typing import List

app = FastAPI(title="P2P Wallet API")

# Create tables
models.Base.metadata.create_all(bind=database.engine)

def get_system_account(db: Session):
    sys_acc = db.query(models.Account).filter(models.Account.is_system == True).first()
    if not sys_acc:
        sys_acc = models.Account(is_system=True, currency="GBP")
        db.add(sys_acc)
        db.commit()
        db.refresh(sys_acc)
    return sys_acc

def get_balance(db: Session, account_id: int) -> int:
    credits = db.query(func.sum(models.LedgerEntry.amount_pence)).filter(
        models.LedgerEntry.account_id == account_id,
        models.LedgerEntry.direction == "credit"
    ).scalar() or 0
    debits = db.query(func.sum(models.LedgerEntry.amount_pence)).filter(
        models.LedgerEntry.account_id == account_id,
        models.LedgerEntry.direction == "debit"
    ).scalar() or 0
    return credits - debits

def check_24h_limit(db: Session, account_id: int, amount: int):
    # Sum of transfers out and withdrawals in last 24h
    twenty_four_hours_ago = datetime.utcnow() - timedelta(days=1)
    
    # We find debits for this account where the transaction type is withdrawal or transfer
    recent_debits = db.query(func.sum(models.LedgerEntry.amount_pence)).join(models.Transaction).filter(
        models.LedgerEntry.account_id == account_id,
        models.LedgerEntry.direction == "debit",
        models.Transaction.type.in_(["withdrawal", "transfer"]),
        models.Transaction.created_at >= twenty_four_hours_ago
    ).scalar() or 0
    
    if recent_debits + amount > 100000: # 1000 GBP = 100,000 pence
        raise HTTPException(status_code=400, detail="Transaction exceeds 24-hour limit of £1,000")

@app.post("/auth/register", response_model=schemas.RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: schemas.RegisterRequest, db: Session = Depends(database.get_db)):
    existing_user = db.query(models.User).filter(models.User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(request.password)
    user = models.User(email=request.email, password_hash=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    account = models.Account(user_id=user.id, currency="GBP", is_system=False)
    db.add(account)
    db.commit()
    
    return schemas.RegisterResponse(user_id=user.id, email=user.email)

@app.post("/auth/login", response_model=schemas.LoginResponse)
def login(request: schemas.LoginRequest, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == request.email).first()
    if not user or not auth.verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = auth.create_access_token(data={"sub": user.email}, expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES))
    return schemas.LoginResponse(access_token=access_token)

@app.get("/accounts/me", response_model=schemas.AccountMeResponse)
def get_my_account(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    balance = get_balance(db, current_user.account.id)
    return schemas.AccountMeResponse(
        account_id=current_user.account.id,
        balance_pence=balance,
        currency=current_user.account.currency
    )

@app.post("/deposits", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def deposit(request: schemas.AmountRequest, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    sys_acc = get_system_account(db)
    
    tx = models.Transaction(type="deposit", status="completed")
    db.add(tx)
    db.commit()
    db.refresh(tx)
    
    # Deposit: Debit System, Credit User
    le1 = models.LedgerEntry(transaction_id=tx.id, account_id=sys_acc.id, amount_pence=request.amount_pence, direction="debit")
    le2 = models.LedgerEntry(transaction_id=tx.id, account_id=current_user.account.id, amount_pence=request.amount_pence, direction="credit")
    
    db.add_all([le1, le2])
    db.commit()
    
    new_balance = get_balance(db, current_user.account.id)
    return schemas.TransactionResponse(transaction_id=tx.id, status=tx.status, balance_pence=new_balance)

@app.post("/withdrawals", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def withdraw(request: schemas.AmountRequest, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    balance = get_balance(db, current_user.account.id)
    if balance < request.amount_pence:
        raise HTTPException(status_code=400, detail="Insufficient funds")
    
    check_24h_limit(db, current_user.account.id, request.amount_pence)
    
    sys_acc = get_system_account(db)
    
    tx = models.Transaction(type="withdrawal", status="completed")
    db.add(tx)
    db.commit()
    db.refresh(tx)
    
    # Withdrawal: Debit User, Credit System
    le1 = models.LedgerEntry(transaction_id=tx.id, account_id=current_user.account.id, amount_pence=request.amount_pence, direction="debit")
    le2 = models.LedgerEntry(transaction_id=tx.id, account_id=sys_acc.id, amount_pence=request.amount_pence, direction="credit")
    
    db.add_all([le1, le2])
    db.commit()
    
    new_balance = get_balance(db, current_user.account.id)
    return schemas.TransactionResponse(transaction_id=tx.id, status=tx.status, balance_pence=new_balance)

@app.post("/transfers", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def transfer(request: schemas.TransferRequest, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    if request.recipient_email == current_user.email:
        raise HTTPException(status_code=400, detail="Cannot transfer to own account")
        
    recipient = db.query(models.User).filter(models.User.email == request.recipient_email).first()
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient not found")
        
    balance = get_balance(db, current_user.account.id)
    if balance < request.amount_pence:
        raise HTTPException(status_code=400, detail="Insufficient funds")
        
    check_24h_limit(db, current_user.account.id, request.amount_pence)
    
    tx = models.Transaction(type="transfer", status="completed")
    db.add(tx)
    db.commit()
    db.refresh(tx)
    
    # Transfer: Debit Sender, Credit Recipient
    le1 = models.LedgerEntry(transaction_id=tx.id, account_id=current_user.account.id, amount_pence=request.amount_pence, direction="debit")
    le2 = models.LedgerEntry(transaction_id=tx.id, account_id=recipient.account.id, amount_pence=request.amount_pence, direction="credit")
    
    db.add_all([le1, le2])
    db.commit()
    
    new_balance = get_balance(db, current_user.account.id)
    return schemas.TransactionResponse(transaction_id=tx.id, status=tx.status, balance_pence=new_balance)

@app.get("/transactions", response_model=List[schemas.TransactionHistoryItem])
def get_transactions(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    entries = db.query(models.LedgerEntry).filter(models.LedgerEntry.account_id == current_user.account.id).all()
    
    history = []
    for entry in entries:
        tx = entry.transaction
        history.append(schemas.TransactionHistoryItem(
            transaction_id=tx.id,
            type=tx.type,
            amount_pence=entry.amount_pence,
            direction=entry.direction,
            status=tx.status,
            created_at=tx.created_at
        ))
    
    return sorted(history, key=lambda x: x.created_at, reverse=True)

@app.post("/transactions/{transaction_id}/reversal", response_model=schemas.ReversalResponse, status_code=status.HTTP_201_CREATED)
def reverse_transaction(transaction_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    original_tx = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not original_tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    if original_tx.type != "transfer" or original_tx.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed transfers can be reversed")
        
    # Check if current_user was the sender
    sender_entry = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.transaction_id == original_tx.id,
        models.LedgerEntry.account_id == current_user.account.id,
        models.LedgerEntry.direction == "debit"
    ).first()
    
    if not sender_entry:
        raise HTTPException(status_code=403, detail="Not authorized to reverse this transaction")
        
    # Find recipient entry
    recipient_entry = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.transaction_id == original_tx.id,
        models.LedgerEntry.account_id != current_user.account.id,
        models.LedgerEntry.direction == "credit"
    ).first()
    
    if not recipient_entry:
        raise HTTPException(status_code=500, detail="Original transaction is corrupted")

    amount = sender_entry.amount_pence

    # Ensure recipient has enough funds to have the transfer reversed (business rule choice, optional but good practice, though instructions say "reversal shall be affected...")
    # Actually BR7 says "A reversal shall be affected... No existing transaction shall be amended." 
    # Let's just create it. (If it drives recipient negative, the ledger supports it, although usually withdrawals don't allow negatives)

    rev_tx = models.Transaction(type="reversal", status="completed", reversed_transaction_id=original_tx.id)
    db.add(rev_tx)
    original_tx.status = "reversed"
    db.commit()
    db.refresh(rev_tx)
    
    # Reversal: Credit Original Sender, Debit Original Recipient
    le1 = models.LedgerEntry(transaction_id=rev_tx.id, account_id=current_user.account.id, amount_pence=amount, direction="credit")
    le2 = models.LedgerEntry(transaction_id=rev_tx.id, account_id=recipient_entry.account_id, amount_pence=amount, direction="debit")
    
    db.add_all([le1, le2])
    db.commit()
    
    return schemas.ReversalResponse(
        transaction_id=rev_tx.id,
        reverses_transaction_id=original_tx.id,
        status=rev_tx.status
    )
