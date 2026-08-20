from pydantic import BaseModel, EmailStr, Field
from typing import List
from datetime import datetime

class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

class RegisterRes(BaseModel):
    user_id: str
    email: str

class LoginReq(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

class LoginRes(BaseModel):
    access_token: str

class AccountRes(BaseModel):
    account_id: str
    balance_pence: int
    currency: str

class AmountReq(BaseModel):
    amount_pence: int = Field(..., gt=0, strict=True)

class TransferReq(BaseModel):
    recipient_email: EmailStr
    amount_pence: int = Field(..., gt=0, strict=True)

class TxRes(BaseModel):
    transaction_id: str
    status: str
    balance_pence: int

class TransactionItem(BaseModel):
    transaction_id: str
    type: str
    amount_pence: int
    direction: str
    status: str
    created_at: datetime

class ReversalRes(BaseModel):
    transaction_id: str
    reverses_transaction_id: str
    status: str
