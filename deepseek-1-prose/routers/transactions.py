# routers/transactions.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from database import get_db
import models
import schemas
from auth import get_current_user

router = APIRouter()

DAILY_LIMIT_PENCE = 100000  # £1000 in pence

def get_daily_total_for_user(user_id: int, db: Session):
    """Get total debits for the current day"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    daily_total = db.query(func.sum(models.Transaction.amount_pence)).filter(
        models.Transaction.user_id == user_id,
        models.Transaction.direction == "debit",
        models.Transaction.status == models.TransactionStatus.COMPLETED,
        models.Transaction.created_at >= today_start,
        models.Transaction.type.in_([models.TransactionType.WITHDRAWAL, models.TransactionType.TRANSFER])
    ).scalar() or 0
    
    return daily_total

@router.post("/deposits", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_deposit(
    deposit_data: schemas.DepositRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    account = db.query(models.Account).filter(models.Account.user_id == current_user.id).with_for_update().first()
    
    # Update balance
    account.balance_pence += deposit_data.amount_pence
    
    # Create transaction record
    transaction = models.Transaction(
        user_id=current_user.id,
        type=models.TransactionType.DEPOSIT,
        amount_pence=deposit_data.amount_pence,
        status=models.TransactionStatus.COMPLETED,
        direction="credit"
    )
    
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    return schemas.TransactionResponse(
        transaction_id=transaction.id,
        status=transaction.status.value,
        balance_pence=account.balance_pence
    )

@router.post("/withdrawals", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_withdrawal(
    withdrawal_data: schemas.WithdrawalRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    account = db.query(models.Account).filter(models.Account.user_id == current_user.id).with_for_update().first()
    
    # Check sufficient balance
    if account.balance_pence < withdrawal_data.amount_pence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds"
        )
    
    # Check daily limit
    daily_total = get_daily_total_for_user(current_user.id, db)
    if daily_total + withdrawal_data.amount_pence > DAILY_LIMIT_PENCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Daily limit of £1000 exceeded"
        )
    
    # Update balance
    account.balance_pence -= withdrawal_data.amount_pence
    
    # Create transaction record
    transaction = models.Transaction(
        user_id=current_user.id,
        type=models.TransactionType.WITHDRAWAL,
        amount_pence=withdrawal_data.amount_pence,
        status=models.TransactionStatus.COMPLETED,
        direction="debit"
    )
    
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    return schemas.TransactionResponse(
        transaction_id=transaction.id,
        status=transaction.status.value,
        balance_pence=account.balance_pence
    )

@router.post("/transfers", response_model=schemas.TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    transfer_data: schemas.TransferRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Validate not sending to self
    if transfer_data.recipient_email == current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer to yourself"
        )
    
    # Get recipient
    recipient = db.query(models.User).filter(models.User.email == transfer_data.recipient_email).first()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found"
        )
    
    # Get sender account with lock
    sender_account = db.query(models.Account).filter(
        models.Account.user_id == current_user.id
    ).with_for_update().first()
    
    # Check sufficient balance
    if sender_account.balance_pence < transfer_data.amount_pence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds"
        )
    
    # Check daily limit
    daily_total = get_daily_total_for_user(current_user.id, db)
    if daily_total + transfer_data.amount_pence > DAILY_LIMIT_PENCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Daily limit of £1000 exceeded"
        )
    
    # Get recipient account with lock
    recipient_account = db.query(models.Account).filter(
        models.Account.user_id == recipient.id
    ).with_for_update().first()
    
    # Perform transfer atomically
    sender_account.balance_pence -= transfer_data.amount_pence
    recipient_account.balance_pence += transfer_data.amount_pence
    
    # Create sender's transaction record
    sender_transaction = models.Transaction(
        user_id=current_user.id,
        type=models.TransactionType.TRANSFER,
        amount_pence=transfer_data.amount_pence,
        status=models.TransactionStatus.COMPLETED,
        direction="debit",
        recipient_email=transfer_data.recipient_email,
        recipient_id=recipient.id
    )
    db.add(sender_transaction)
    
    # Create recipient's transaction record
    recipient_transaction = models.Transaction(
        user_id=recipient.id,
        type=models.TransactionType.TRANSFER,
        amount_pence=transfer_data.amount_pence,
        status=models.TransactionStatus.COMPLETED,
        direction="credit",
        recipient_email=current_user.email,
        recipient_id=current_user.id
    )
    db.add(recipient_transaction)
    
    db.commit()
    db.refresh(sender_transaction)
    
    return schemas.TransactionResponse(
        transaction_id=sender_transaction.id,
        status=sender_transaction.status.value,
        balance_pence=sender_account.balance_pence
    )

@router.get("/transactions", response_model=list[schemas.TransactionHistory])
def get_transactions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    transactions = db.query(models.Transaction).filter(
        models.Transaction.user_id == current_user.id
    ).order_by(models.Transaction.created_at.desc()).all()
    
    return [
        schemas.TransactionHistory(
            transaction_id=t.id,
            type=t.type.value,
            amount_pence=t.amount_pence,
            direction=t.direction,
            status=t.status.value,
            created_at=t.created_at
        ) for t in transactions
    ]

@router.post("/transactions/{transaction_id}/reversal", response_model=schemas.ReversalResponse, status_code=status.HTTP_201_CREATED)
def reverse_transaction(
    transaction_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get the original transaction
    original_transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.user_id == current_user.id
    ).with_for_update().first()
    
    if not original_transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    
    # Validate transaction can be reversed
    if original_transaction.status != models.TransactionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction already reversed"
        )
    
    if original_transaction.type not in [models.TransactionType.TRANSFER]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only transfers can be reversed"
        )
    
    if original_transaction.direction != "debit":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only sent transfers can be reversed"
        )
    
    # Get recipient
    recipient = db.query(models.User).filter(
        models.User.id == original_transaction.recipient_id
    ).first()
    
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient no longer exists"
        )
    
    # Get accounts with locks
    sender_account = db.query(models.Account).filter(
        models.Account.user_id == current_user.id
    ).with_for_update().first()
    
    recipient_account = db.query(models.Account).filter(
        models.Account.user_id == recipient.id
    ).with_for_update().first()
    
    # Check recipient has enough balance
    if recipient_account.balance_pence < original_transaction.amount_pence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient has insufficient funds for reversal"
        )
    
    # Perform reversal
    sender_account.balance_pence += original_transaction.amount_pence
    recipient_account.balance_pence -= original_transaction.amount_pence
    
    # Mark original transaction as reversed
    original_transaction.status = models.TransactionStatus.REVERSED
    
    # Create reversal transaction for sender
    reversal_transaction = models.Transaction(
        user_id=current_user.id,
        type=models.TransactionType.REVERSAL,
        amount_pence=original_transaction.amount_pence,
        status=models.TransactionStatus.COMPLETED,
        direction="credit",
        recipient_email=recipient.email,
        recipient_id=recipient.id,
        reversed_transaction_id=original_transaction.id
    )
    db.add(reversal_transaction)
    
    # Create reversal transaction for recipient
    recipient_reversal = models.Transaction(
        user_id=recipient.id,
        type=models.TransactionType.REVERSAL,
        amount_pence=original_transaction.amount_pence,
        status=models.TransactionStatus.COMPLETED,
        direction="debit",
        recipient_email=current_user.email,
        recipient_id=current_user.id,
        reversed_transaction_id=original_transaction.id
    )
    db.add(recipient_reversal)
    
    db.commit()
    db.refresh(reversal_transaction)
    
    return schemas.ReversalResponse(
        transaction_id=reversal_transaction.id,
        reverses_transaction_id=original_transaction.id,
        status=reversal_transaction.status.value
    )