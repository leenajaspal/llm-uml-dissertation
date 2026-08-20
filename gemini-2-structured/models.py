from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    account = relationship("Account", back_populates="user", uselist=False)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True) # Null for system account
    currency = Column(String, default="GBP")
    is_system = Column(Boolean, default=False)
    user = relationship("User", back_populates="account")
    ledger_entries = relationship("LedgerEntry", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False) # deposit, withdrawal, transfer, reversal
    status = Column(String, default="completed") # completed, reversed
    created_at = Column(DateTime, default=datetime.utcnow)
    reversed_transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    entries = relationship("LedgerEntry", back_populates="transaction")

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    amount_pence = Column(Integer, nullable=False)
    direction = Column(String, nullable=False) # debit, credit
    
    transaction = relationship("Transaction", back_populates="entries")
    account = relationship("Account", back_populates="ledger_entries")
