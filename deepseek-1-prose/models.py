# models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
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
    PENDING = "pending"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    account = relationship("Account", back_populates="user", uselist=False)
    transactions = relationship("Transaction", back_populates="user")

class Account(Base):
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    balance_pence = Column(Integer, default=0, nullable=False)
    currency = Column(String, default="GBP", nullable=False)
    
    user = relationship("User", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    amount_pence = Column(Integer, nullable=False)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.COMPLETED, nullable=False)
    direction = Column(String, nullable=False)  # "credit" or "debit"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # For transfers
    recipient_email = Column(String, nullable=True)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # For reversals
    reversed_transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    
    user = relationship("User", back_populates="transactions")