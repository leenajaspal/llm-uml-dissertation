"""Domain entities as SQLAlchemy models.

Balances are NEVER stored as a mutable field (BR6). An account balance is
always derived from the sum of its ledger entries (see ledger.account_balance).
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)

from database import Base

# Enumerated string values used across the domain.
TX_DEPOSIT = "deposit"
TX_WITHDRAWAL = "withdrawal"
TX_TRANSFER = "transfer"
TX_REVERSAL = "reversal"

STATUS_COMPLETED = "completed"
STATUS_REVERSED = "reversed"

DIR_DEBIT = "debit"
DIR_CREDIT = "credit"


class User(Base):
    """A registered user, identified by a unique email address (FR1)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    # NFR1: one-way hash + per-user salt. The plaintext password is never
    # stored and cannot be recovered from these values.
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)


class Account(Base):
    """An account holding value, denominated in GBP.

    A regular account belongs to exactly one user (one account per user).
    The single system account has user_id = NULL and is_system = True; it
    represents funds held outside the application and is not user-accessible.
    """

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    currency = Column(String, nullable=False, default="GBP")
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)


class Transaction(Base):
    """A single movement of value.

    ``amount_pence`` is the value of the movement (equal to both ledger
    entries). ``initiating_user_id`` records who performed the transaction;
    for a transfer this is the sending party (used for reversal authorisation
    and for the rolling daily limit).
    """

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)  # deposit | withdrawal | transfer | reversal
    status = Column(String, nullable=False)  # completed | reversed
    amount_pence = Column(Integer, nullable=False)
    initiating_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reverses_transaction_id = Column(
        Integer, ForeignKey("transactions.id"), nullable=True
    )
    created_at = Column(DateTime, nullable=False)


class LedgerEntry(Base):
    """One line of the double-entry ledger (BR4).

    ``amount_pence`` is always a positive value; ``direction`` distinguishes
    debit from credit. Every transaction has exactly two entries: one debit
    and one credit of equal value against two different accounts, so the sum
    of all ledger entries in the system is always zero.
    """

    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount_pence = Column(Integer, nullable=False)  # always positive
    direction = Column(String, nullable=False)  # debit | credit


# Helpful composite indexes for the balance and history queries.
Index("ix_ledger_account", LedgerEntry.account_id)
Index("ix_ledger_transaction", LedgerEntry.transaction_id)
Index(
    "ix_tx_initiator_type_time",
    Transaction.initiating_user_id,
    Transaction.type,
    Transaction.created_at,
)
