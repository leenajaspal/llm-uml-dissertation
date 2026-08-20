from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    account = relationship("Account", back_populates="user", uselist=False)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    balance_pence = Column(Integer, default=0, nullable=False)
    currency = Column(String, default="GBP", nullable=False)
    
    user = relationship("User", back_populates="account")
    transactions = relationship("Transaction", back_populates="account", foreign_keys='Transaction.account_id')

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(String, nullable=False) # DEPOSIT, WITHDRAWAL, TRANSFER
    amount_pence = Column(Integer, nullable=False)
    direction = Column(String, nullable=False) # CREDIT, DEBIT
    status = Column(String, default="COMPLETED", nullable=False) # COMPLETED, REVERSED, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Track the opposing side of a transfer (e.g., the recipient's CREDIT tx ID)
    related_transaction_id = Column(Integer, nullable=True)
    # Track the transaction this reversal applies to
    reverses_transaction_id = Column(Integer, nullable=True)

    account = relationship("Account", foreign_keys=[account_id])