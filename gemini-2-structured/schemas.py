from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional
from datetime import datetime

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

class AccountMeResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str

class AmountRequest(BaseModel):
    amount_pence: int
    
    @field_validator('amount_pence')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be a positive integer')
        return v

class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int
    
    @field_validator('amount_pence')
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be a positive integer')
        return v

class TransactionResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int

class ReversalResponse(BaseModel):
    transaction_id: int
    reverses_transaction_id: int
    status: str

class TransactionHistoryItem(BaseModel):
    transaction_id: int
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: datetime
