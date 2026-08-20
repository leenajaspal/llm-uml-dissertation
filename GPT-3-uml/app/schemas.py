from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, field_validator


MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807
PositivePence = Annotated[StrictInt, Field(gt=0, le=MAX_SQLITE_INTEGER)]


def normalise_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("email must be a string")
    email = value.strip().lower()
    if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("email must be a valid email address")
    if len(email) > 320:
        raise ValueError("email is too long")
    return email


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalise_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalise_email(value)


class RegisterResponse(BaseModel):
    user_id: str
    email: str


class LoginResponse(BaseModel):
    access_token: str


class AccountMeResponse(BaseModel):
    account_id: str
    balance_pence: int
    currency: str


class AmountRequest(BaseModel):
    amount_pence: PositivePence


class TransferRequest(BaseModel):
    recipient_email: str
    amount_pence: PositivePence

    @field_validator("recipient_email")
    @classmethod
    def validate_recipient_email(cls, value: str) -> str:
        return normalise_email(value)


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
    created_at: datetime


class ReversalResponse(BaseModel):
    transaction_id: str
    reverses_transaction_id: str
    status: str
