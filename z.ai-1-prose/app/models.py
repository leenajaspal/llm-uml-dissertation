"""Pydantic request/response models."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    user_id: int
    email: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str


# ---------- Accounts ----------
class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str


# ---------- Money movement ----------
class DepositRequest(BaseModel):
    amount_pence: int = Field(gt=0)


class WithdrawalRequest(BaseModel):
    amount_pence: int = Field(gt=0)


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int = Field(gt=0)


class MoneyMovementResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int


# ---------- Transactions ----------
class TransactionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    transaction_id: int
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: str


class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str