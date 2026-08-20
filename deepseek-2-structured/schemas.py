from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str

class UserResponse(BaseModel):
    user_id: int
    email: str

class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str

class AmountRequest(BaseModel):
    amount_pence: int

    @validator('amount_pence')
    def validate_amount(cls, v):
        if not isinstance(v, int):
            raise ValueError('Amount must be an integer')
        if v <= 0:
            raise ValueError('Amount must be a positive integer')
        if v > 100000000:  # 1 million GBP max
            raise ValueError('Amount exceeds maximum allowed')
        return v

class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int

    @validator('amount_pence')
    def validate_amount(cls, v):
        if not isinstance(v, int):
            raise ValueError('Amount must be an integer')
        if v <= 0:
            raise ValueError('Amount must be a positive integer')
        if v > 100000000:
            raise ValueError('Amount exceeds maximum allowed')
        return v

class TransactionResponse(BaseModel):
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

class OperationResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int