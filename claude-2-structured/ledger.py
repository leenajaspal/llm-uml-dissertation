"""Double-entry ledger operations.

Balances are always derived from ledger entries (BR6). A balance is the sum of
credit amounts minus the sum of debit amounts for an account, so:

    deposit  -> credit user  -> balance increases
    withdraw -> debit  user  -> balance decreases
    transfer -> debit sender, credit recipient
    reversal -> debit recipient, credit sender (moves value the opposite way)
"""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import DAILY_WINDOW_HOURS
from models import (
    DIR_CREDIT,
    DIR_DEBIT,
    STATUS_COMPLETED,
    TX_TRANSFER,
    TX_WITHDRAWAL,
    Account,
    LedgerEntry,
    Transaction,
)


def get_system_account(db: Session) -> Account:
    return db.query(Account).filter(Account.is_system.is_(True)).first()


def get_user_account(db: Session, user_id: int) -> Account:
    return db.query(Account).filter(Account.user_id == user_id).first()


def account_balance(db: Session, account_id: int) -> int:
    """Derive an account balance from its ledger entries (BR6)."""
    credits = db.query(
        func.coalesce(func.sum(LedgerEntry.amount_pence), 0)
    ).filter(
        LedgerEntry.account_id == account_id,
        LedgerEntry.direction == DIR_CREDIT,
    ).scalar()
    debits = db.query(
        func.coalesce(func.sum(LedgerEntry.amount_pence), 0)
    ).filter(
        LedgerEntry.account_id == account_id,
        LedgerEntry.direction == DIR_DEBIT,
    ).scalar()
    return int(credits) - int(debits)


def spent_last_24h(db: Session, user_id: int, now: datetime) -> int:
    """Total value of transfers + withdrawals a user made in the rolling
    24-hour window ending at ``now`` (BR3). Deposits and reversals are excluded.

    All matching transfers/withdrawals in the window count, whether or not a
    transfer was later reversed: the value did move at the time it was made.
    """
    since = now - timedelta(hours=DAILY_WINDOW_HOURS)
    total = db.query(
        func.coalesce(func.sum(Transaction.amount_pence), 0)
    ).filter(
        Transaction.initiating_user_id == user_id,
        Transaction.type.in_([TX_TRANSFER, TX_WITHDRAWAL]),
        Transaction.created_at >= since,
    ).scalar()
    return int(total)


def post_transaction(
    db: Session,
    *,
    tx_type: str,
    amount: int,
    debit_account_id: int,
    credit_account_id: int,
    initiating_user_id,
    created_at: datetime,
    status: str = STATUS_COMPLETED,
    reverses_transaction_id=None,
) -> Transaction:
    """Create one transaction and its two balanced ledger entries.

    This only stages the rows on the session; the caller commits so that the
    transaction and both entries are written as a single atomic unit (NFR5,
    BR4). ``debit_account_id`` and ``credit_account_id`` must differ.
    """
    if debit_account_id == credit_account_id:
        raise ValueError("A transaction must move value between two accounts")

    tx = Transaction(
        type=tx_type,
        status=status,
        amount_pence=amount,
        initiating_user_id=initiating_user_id,
        reverses_transaction_id=reverses_transaction_id,
        created_at=created_at,
    )
    db.add(tx)
    db.flush()  # assign tx.id without committing

    db.add(
        LedgerEntry(
            transaction_id=tx.id,
            account_id=debit_account_id,
            amount_pence=amount,
            direction=DIR_DEBIT,
        )
    )
    db.add(
        LedgerEntry(
            transaction_id=tx.id,
            account_id=credit_account_id,
            amount_pence=amount,
            direction=DIR_CREDIT,
        )
    )
    return tx
