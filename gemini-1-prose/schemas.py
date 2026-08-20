from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterResponse(BaseModel):
    user_id: int
    email: str

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str

class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str

class AmountRequest(BaseModel):
    amount_pence: int

class TransactionResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int

class TransferRequest(BaseModel):
    recipient_email: str
    amount_pence: int

class TransactionHistoryItem(BaseModel):
    transaction_id: int
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: datetime

class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str