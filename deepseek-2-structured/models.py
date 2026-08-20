from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SqlEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from database import Base

class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    REVERSAL = "reversal"

class TransactionStatus(str, enum.Enum):
    COMPLETED = "completed"
    REVERSED = "reversed"

class Direction(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    account = relationship("Account", back_populates="user", uselist=False)

class Account(Base):
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    is_system = Column(Integer, default=0)
    currency = Column(String, default="GBP")
    
    user = relationship("User", back_populates="account")
    ledger_entries = relationship("LedgerEntry", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(SqlEnum(TransactionType), nullable=False)
    status = Column(SqlEnum(TransactionStatus), default=TransactionStatus.COMPLETED)
    created_at = Column(DateTime, default=datetime.utcnow)
    reversed_by_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    
    reverses = relationship("Transaction", remote_side=[id], foreign_keys=[reversed_by_id])
    ledger_entries = relationship("LedgerEntry", back_populates="transaction")

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount_pence = Column(Integer, nullable=False)
    direction = Column(SqlEnum(Direction), nullable=False)
    
    transaction = relationship("Transaction", back_populates="ledger_entries")
    account = relationship("Account", back_populates="ledger_entries")