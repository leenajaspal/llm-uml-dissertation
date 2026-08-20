from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
from models import (
    Account, Transaction, LedgerEntry, User,
    TransactionType, TransactionStatus, Direction
)
from services.account_service import get_account_balance, get_system_account

def check_daily_limit(db: Session, account: Account, amount_pence: int) -> bool:
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    
    recent_outgoing = db.query(LedgerEntry).join(Transaction).filter(
        and_(
            LedgerEntry.account_id == account.id,
            LedgerEntry.direction == Direction.DEBIT,
            Transaction.created_at >= cutoff_time,
            Transaction.type.in_([TransactionType.WITHDRAWAL, TransactionType.TRANSFER]),
            Transaction.status == TransactionStatus.COMPLETED
        )
    ).all()
    
    total_outgoing = sum(entry.amount_pence for entry in recent_outgoing)
    return (total_outgoing + amount_pence) <= 100000  # £1,000 in pence

def process_deposit(db: Session, account: Account, amount_pence: int) -> tuple[Transaction, int]:
    system_account = get_system_account(db)
    
    transaction = Transaction(type=TransactionType.DEPOSIT, status=TransactionStatus.COMPLETED)
    db.add(transaction)
    
    # Debit system account (money goes out of system)
    debit_entry = LedgerEntry(
        transaction=transaction,
        account_id=system_account.id,
        amount_pence=amount_pence,
        direction=Direction.DEBIT
    )
    db.add(debit_entry)
    
    # Credit user account (money comes into user)
    credit_entry = LedgerEntry(
        transaction=transaction,
        account_id=account.id,
        amount_pence=amount_pence,
        direction=Direction.CREDIT
    )
    db.add(credit_entry)
    
    db.commit()
    db.refresh(transaction)
    
    balance = get_account_balance(account)
    return transaction, balance

def process_withdrawal(db: Session, account: Account, amount_pence: int) -> tuple[Transaction, int]:
    current_balance = get_account_balance(account)
    
    if current_balance < amount_pence:
        raise ValueError("Insufficient funds")
    
    if not check_daily_limit(db, account, amount_pence):
        raise ValueError("Daily withdrawal/transfer limit of £1,000 exceeded")
    
    system_account = get_system_account(db)
    
    transaction = Transaction(type=TransactionType.WITHDRAWAL, status=TransactionStatus.COMPLETED)
    db.add(transaction)
    
    # Debit user account (money leaves user)
    debit_entry = LedgerEntry(
        transaction=transaction,
        account_id=account.id,
        amount_pence=amount_pence,
        direction=Direction.DEBIT
    )
    db.add(debit_entry)
    
    # Credit system account (money goes into system)
    credit_entry = LedgerEntry(
        transaction=transaction,
        account_id=system_account.id,
        amount_pence=amount_pence,
        direction=Direction.CREDIT
    )
    db.add(credit_entry)
    
    db.commit()
    db.refresh(transaction)
    
    balance = get_account_balance(account)
    return transaction, balance

def process_transfer(db: Session, sender_account: Account, recipient_email: str, amount_pence: int) -> tuple[Transaction, int]:
    current_balance = get_account_balance(sender_account)
    
    if current_balance < amount_pence:
        raise ValueError("Insufficient funds")
    
    recipient_user = db.query(User).filter(User.email == recipient_email).first()
    if not recipient_user:
        raise ValueError("Recipient not found")
    
    if recipient_user.id == sender_account.user_id:
        raise ValueError("Cannot transfer to your own account")
    
    if not check_daily_limit(db, sender_account, amount_pence):
        raise ValueError("Daily withdrawal/transfer limit of £1,000 exceeded")
    
    recipient_account = db.query(Account).filter(Account.user_id == recipient_user.id).first()
    
    transaction = Transaction(type=TransactionType.TRANSFER, status=TransactionStatus.COMPLETED)
    db.add(transaction)
    
    # Debit sender account
    debit_entry = LedgerEntry(
        transaction=transaction,
        account_id=sender_account.id,
        amount_pence=amount_pence,
        direction=Direction.DEBIT
    )
    db.add(debit_entry)
    
    # Credit recipient account
    credit_entry = LedgerEntry(
        transaction=transaction,
        account_id=recipient_account.id,
        amount_pence=amount_pence,
        direction=Direction.CREDIT
    )
    db.add(credit_entry)
    
    db.commit()
    db.refresh(transaction)
    
    balance = get_account_balance(sender_account)
    return transaction, balance

def reverse_transfer(db: Session, transaction_id: int, user_id: int) -> Transaction:
    original_txn = db.query(Transaction).filter(
        and_(
            Transaction.id == transaction_id,
            Transaction.type == TransactionType.TRANSFER
        )
    ).first()
    
    if not original_txn:
        raise ValueError("Transaction not found")
    
    if original_txn.status == TransactionStatus.REVERSED:
        raise ValueError("Transaction already reversed")
    
    # Verify the requesting user was the sender
    sender_entry = db.query(LedgerEntry).filter(
        and_(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.direction == Direction.DEBIT
        )
    ).first()
    
    sender_account = db.query(Account).filter(Account.id == sender_entry.account_id).first()
    if sender_account.user_id != user_id:
        raise ValueError("Only the sender can reverse a transfer")
    
    # Get the recipient entry
    recipient_entry = db.query(LedgerEntry).filter(
        and_(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.direction == Direction.CREDIT
        )
    ).first()
    
    recipient_account = db.query(Account).filter(Account.id == recipient_entry.account_id).first()
    
    # Create reversal transaction
    reversal_txn = Transaction(
        type=TransactionType.REVERSAL,
        status=TransactionStatus.COMPLETED,
        reversed_by_id=transaction_id
    )
    db.add(reversal_txn)
    
    # Credit sender (give money back)
    credit_entry = LedgerEntry(
        transaction=reversal_txn,
        account_id=sender_account.id,
        amount_pence=sender_entry.amount_pence,
        direction=Direction.CREDIT
    )
    db.add(credit_entry)
    
    # Debit recipient (take money back)
    debit_entry = LedgerEntry(
        transaction=reversal_txn,
        account_id=recipient_account.id,
        amount_pence=sender_entry.amount_pence,
        direction=Direction.DEBIT
    )
    db.add(debit_entry)
    
    # Mark original as reversed
    original_txn.status = TransactionStatus.REVERSED
    
    db.commit()
    db.refresh(reversal_txn)
    
    return reversal_txn

def get_transaction_history(db: Session, account: Account) -> list:
    entries = db.query(LedgerEntry).filter(
        LedgerEntry.account_id == account.id
    ).order_by(LedgerEntry.id.desc()).all()
    
    transactions = []
    for entry in entries:
        txn = entry.transaction
        # Find the other entry to determine the full amount
        other_entry = db.query(LedgerEntry).filter(
            and_(
                LedgerEntry.transaction_id == txn.id,
                LedgerEntry.id != entry.id
            )
        ).first()
        
        transactions.append({
            "transaction_id": txn.id,
            "type": txn.type.value,
            "amount_pence": entry.amount_pence,
            "direction": entry.direction.value,
            "status": txn.status.value,
            "created_at": txn.created_at
        })
    
    return transactions