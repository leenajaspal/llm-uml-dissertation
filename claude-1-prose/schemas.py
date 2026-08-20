"""Request and response models.

Field names here match the API contract exactly. All amounts are integer pence.
"""
from pydantic import BaseModel, EmailStr, Field

from config import MAX_TXN_PENCE

# --- Auth --------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    user_id: int
    email: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str


# --- Account -----------------------------------------------------------------


class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str


# --- Money movement ----------------------------------------------------------


class AmountRequest(BaseModel):
    amount_pence: int = Field(gt=0, le=MAX_TXN_PENCE)


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int = Field(gt=0, le=MAX_TXN_PENCE)


class MoneyResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int


class TransactionItem(BaseModel):
    transaction_id: int
    type: str
    amount_pence: int
    direction: str  # 'credit' (money in) | 'debit' (money out)
    status: str
    created_at: str


class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str
