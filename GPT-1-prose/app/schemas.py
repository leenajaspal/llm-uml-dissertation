from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MAX_AMOUNT_PENCE = 10_000_000_000


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class RegisterResponse(BaseModel):
    user_id: int
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str


class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str


class AmountRequest(BaseModel):
    amount_pence: int = Field(gt=0, le=MAX_AMOUNT_PENCE)


class DepositWithdrawalResponse(BaseModel):
    transaction_id: str
    status: str
    balance_pence: int


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int = Field(gt=0, le=MAX_AMOUNT_PENCE)


class TransferResponse(BaseModel):
    transaction_id: str
    status: str
    balance_pence: int


class TransactionResponse(BaseModel):
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
