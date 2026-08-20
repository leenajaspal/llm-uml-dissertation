from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)

class RegisterResponse(BaseModel):
    user_id: int
    email: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str

class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str

class DepositRequest(BaseModel):
    amount_pence: int = Field(..., gt=0, description="Amount in pence, must be positive")

    @validator('amount_pence')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        if not isinstance(v, int):
            raise ValueError('Amount must be an integer')
        return v

class WithdrawalRequest(BaseModel):
    amount_pence: int = Field(..., gt=0, description="Amount in pence, must be positive")

    @validator('amount_pence')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        if not isinstance(v, int):
            raise ValueError('Amount must be an integer')
        return v

class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int = Field(..., gt=0, description="Amount in pence, must be positive")

    @validator('amount_pence')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        if not isinstance(v, int):
            raise ValueError('Amount must be an integer')
        return v

class TransactionResponse(BaseModel):
    transaction_id: int
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]

class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str

class DepositWithdrawalResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int

class ErrorResponse(BaseModel):
    detail: str