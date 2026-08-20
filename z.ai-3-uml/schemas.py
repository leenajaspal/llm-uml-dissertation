from pydantic import BaseModel, EmailStr, Field

# Representable range guard: well within SQLite INTEGER (8-byte signed) range
MAX_PENCE = 2 ** 62


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


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


class AmountRequest(BaseModel):
    amount_pence: int = Field(..., gt=0, le=MAX_PENCE, strict=True)


class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount_pence: int = Field(..., gt=0, le=MAX_PENCE, strict=True)


class TransactionResultResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int


class TransactionResponse(BaseModel):
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