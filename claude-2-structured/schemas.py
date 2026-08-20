"""Request and response bodies.

Field names match the specification exactly. Monetary amounts use a strict
integer type so that zero, negative, fractional, string and out-of-range
values are rejected before any account is touched (BR11 / NFR4).
"""
from typing import Annotated, List

from pydantic import BaseModel, EmailStr, Field

from config import MAX_AMOUNT_PENCE

# Strict positive integer pence. strict=True rejects floats (e.g. 10.5, and
# also 10.0 which JSON parses as a float) and strings; gt=0 rejects zero and
# negatives; le bounds the representable range.
AmountPence = Annotated[int, Field(strict=True, gt=0, le=MAX_AMOUNT_PENCE)]


# --- Auth --------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterResponse(BaseModel):
    user_id: int
    email: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str


# --- Account -----------------------------------------------------------------
class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str


# --- Movements (deposit / withdrawal / transfer) -----------------------------
class AmountRequest(BaseModel):
    amount_pence: AmountPence


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: AmountPence


class MovementResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int


# --- History -----------------------------------------------------------------
class TransactionListItem(BaseModel):
    transaction_id: int
    type: str
    amount_pence: int
    direction: str  # debit | credit, from the perspective of the user's account
    status: str
    created_at: str


TransactionList = List[TransactionListItem]


# --- Reversal ----------------------------------------------------------------
class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str
