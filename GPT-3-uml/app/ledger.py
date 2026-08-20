from datetime import timedelta
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .models import Account, LedgerEntry, Transaction, utcnow


SYSTEM_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"
GBP = "GBP"
DAILY_OUTGOING_LIMIT_PENCE = 100_000


def ensure_system_account(db: Session) -> Account:
    system_account = db.get(Account, SYSTEM_ACCOUNT_ID)
    if system_account is None:
        system_account = Account(
            account_id=SYSTEM_ACCOUNT_ID,
            user_id=None,
            currency=GBP,
            is_system=True,
        )
        db.add(system_account)
        db.commit()
    return system_account


def get_user_account(db: Session, user_id: str) -> Account:
    account = db.scalar(select(Account).where(Account.user_id == user_id))
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User account is missing",
        )
    return account


def get_balance_pence(db: Session, account_id: str) -> int:
    credit_total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_pence), 0)).where(
            LedgerEntry.account_id == account_id,
            LedgerEntry.direction == "credit",
        )
    )
    debit_total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_pence), 0)).where(
            LedgerEntry.account_id == account_id,
            LedgerEntry.direction == "debit",
        )
    )
    return int(credit_total or 0) - int(debit_total or 0)


def get_outgoing_total_last_24h(db: Session, account_id: str) -> int:
    cutoff = utcnow() - timedelta(hours=24)
    total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_pence), 0))
        .join(Transaction, Transaction.transaction_id == LedgerEntry.transaction_id)
        .where(
            LedgerEntry.account_id == account_id,
            LedgerEntry.direction == "debit",
            Transaction.type.in_(("withdrawal", "transfer")),
            Transaction.created_at >= cutoff,
        )
    )
    return int(total or 0)


def enforce_daily_outgoing_limit(db: Session, account_id: str, amount_pence: int) -> None:
    total = get_outgoing_total_last_24h(db, account_id)
    if total + amount_pence > DAILY_OUTGOING_LIMIT_PENCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rolling 24-hour outgoing limit exceeded",
        )


def create_double_entry_transaction(
    db: Session,
    transaction_type: str,
    debit_account_id: str,
    credit_account_id: str,
    amount_pence: int,
    reverses_transaction_id: str | None = None,
) -> Transaction:
    if debit_account_id == credit_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debit and credit accounts must be different",
        )

    transaction = Transaction(
        type=transaction_type,
        status="completed",
        reverses_transaction_id=reverses_transaction_id,
    )
    db.add(transaction)
    db.flush()

    db.add_all(
        [
            LedgerEntry(
                transaction_id=transaction.transaction_id,
                account_id=debit_account_id,
                amount_pence=amount_pence,
                direction="debit",
            ),
            LedgerEntry(
                transaction_id=transaction.transaction_id,
                account_id=credit_account_id,
                amount_pence=amount_pence,
                direction="credit",
            ),
        ]
    )
    db.flush()
    return transaction


def assert_transaction_has_balanced_entries(entries: Iterable[LedgerEntry]) -> None:
    entries = list(entries)
    if len(entries) != 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction does not have exactly two ledger entries",
        )

    debits = [entry for entry in entries if entry.direction == "debit"]
    credits = [entry for entry in entries if entry.direction == "credit"]
    if len(debits) != 1 or len(credits) != 1:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction is not double-entry balanced",
        )

    if debits[0].amount_pence != credits[0].amount_pence:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction ledger entries do not match",
        )

    if debits[0].account_id == credits[0].account_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction ledger entries use the same account",
        )
