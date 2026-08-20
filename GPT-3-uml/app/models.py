import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    # SQLite stores datetimes without timezone metadata; all datetimes are UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    account: Mapped["Account"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User | None] = relationship(back_populates="account")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="account")

    __table_args__ = (
        CheckConstraint("currency = 'GBP'", name="ck_accounts_currency_gbp"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    reverses_transaction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("transactions.transaction_id"),
        nullable=True,
    )

    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('deposit', 'withdrawal', 'transfer', 'reversal')",
            name="ck_transactions_type",
        ),
        CheckConstraint(
            "status IN ('completed', 'reversed')",
            name="ck_transactions_status",
        ),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    ledger_entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.transaction_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="ledger_entries")
    account: Mapped[Account] = relationship(back_populates="ledger_entries")

    __table_args__ = (
        CheckConstraint("amount_pence > 0", name="ck_ledger_amount_positive"),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_ledger_direction"),
        Index("ix_ledger_account_transaction", "account_id", "transaction_id"),
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    user: Mapped[User] = relationship()
