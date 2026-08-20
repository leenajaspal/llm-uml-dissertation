import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

def get_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, default=get_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    account = relationship("Account", back_populates="user", uselist=False)

class Account(Base):
    __tablename__ = "accounts"
    account_id = Column(String, primary_key=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.user_id"), unique=True, nullable=True)
    currency = Column(String, default="GBP")
    user = relationship("User", back_populates="account")
    entries = relationship("LedgerEntry", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(String, primary_key=True, default=get_uuid)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="completed")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reverses_transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=True)

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    ledger_entry_id = Column(String, primary_key=True, default=get_uuid)
    transaction_id = Column(String, ForeignKey("transactions.transaction_id"), nullable=False)
    account_id = Column(String, ForeignKey("accounts.account_id"), nullable=False)
    amount_pence = Column(Integer, nullable=False)
    direction = Column(String, nullable=False)
    account = relationship("Account", back_populates="entries")
