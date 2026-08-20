"""Pydantic request and response models for the public API."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import MAX_AMOUNT_PENCE


PositivePence = Annotated[int, Field(strict=True, gt=0, le=MAX_AMOUNT_PENCE)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("email must be a valid email address")
        return cleaned


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("email must be a valid email address")
        return cleaned


class AmountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_pence: PositivePence


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_email: str = Field(min_length=3, max_length=320)
    amount_pence: PositivePence

    @field_validator("recipient_email")
    @classmethod
    def normalize_recipient_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("recipient_email must be a valid email address")
        return cleaned


class RegisterResponse(BaseModel):
    user_id: str
    email: str


class LoginResponse(BaseModel):
    access_token: str


class AccountResponse(BaseModel):
    account_id: str
    balance_pence: int
    currency: str


class MoneyMovementResponse(BaseModel):
    transaction_id: str
    status: str
    balance_pence: int


class TransactionHistoryItem(BaseModel):
    transaction_id: str
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: str


class ReversalResponse(BaseModel):
    transaction_id: str
    reverses_transaction_id: str
    status: str
