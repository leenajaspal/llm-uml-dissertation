# schemas.py
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    
    @validator('password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    user_id: int
    email: str
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str

class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str
    
    class Config:
        from_attributes = True

class DepositRequest(BaseModel):
    amount_pence: int
    
    @validator('amount_pence')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v

class WithdrawalRequest(BaseModel):
    amount_pence: int
    
    @validator('amount_pence')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v

class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int
    
    @validator('amount_pence')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v

class TransactionResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int
    
    class Config:
        from_attributes = True

class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str
    
    class Config:
        from_attributes = True

class TransactionHistory(BaseModel):
    transaction_id: int
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True