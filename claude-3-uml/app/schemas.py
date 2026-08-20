"""Request and response models.

Field names match the API contract exactly. Monetary inputs are validated
strictly (BR11, NFR4): an amount must be a *positive whole number of pence*.
Zero, negative, fractional, non-numeric and out-of-range values are rejected
before any account is touched.
"""

from typing import Annotated, List, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from .config import MAX_AMOUNT_PENCE

# A strict integer amount in pence. ``strict=True`` means a JSON float such as
# 10.5 or 10.0, or a string such as "10", is rejected rather than coerced;
# booleans are rejected too. gt/le enforce positivity and the representable
# range.
AmountPence = Annotated[
    int, Field(strict=True, gt=0, le=MAX_AMOUNT_PENCE)
]

Password = Annotated[
    str, StringConstraints(min_length=8, max_length=256)
]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password


class RegisterResponse(BaseModel):
    user_id: int
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str


# --------------------------------------------------------------------------- #
# Money movements
# --------------------------------------------------------------------------- #
class AmountRequest(BaseModel):
    amount_pence: AmountPence


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: AmountPence


class MovementResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
class TransactionItem(BaseModel):
    transaction_id: int
    type: Literal["deposit", "withdrawal", "transfer", "reversal"]
    amount_pence: int
    direction: Literal["debit", "credit"]
    status: Literal["completed", "reversed"]
    created_at: str


TransactionList = List[TransactionItem]


class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ErrorResponse(BaseModel):
    detail: str
