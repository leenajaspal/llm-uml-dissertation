from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from database import init_db
from models import UserModel, AccountModel, TransactionModel
from auth import hash_password, verify_password, create_access_token, decode_access_token
from schemas import *
from datetime import datetime

app = FastAPI(title="Payments Wallet API", version="1.0.0")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

# Security scheme
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get the current authenticated user."""
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    user_id = int(payload.get("sub"))
    user = UserModel.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

# Authentication endpoints
@app.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """Register a new user."""
    # Check if user already exists
    existing_user = UserModel.get_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    
    # Hash password and create user
    password_hash = hash_password(request.password)
    user_id = UserModel.create(request.email, password_hash)
    
    return RegisterResponse(user_id=user_id, email=request.email)

@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login and get access token."""
    user = UserModel.get_by_email(request.email)
    
    if not user or not verify_password(request.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Create access token
    access_token = create_access_token(user['user_id'], user['email'])
    
    return LoginResponse(access_token=access_token)

# Account endpoints
@app.get("/accounts/me", response_model=AccountResponse)
async def get_my_account(current_user: dict = Depends(get_current_user)):
    """Get current user's account details."""
    account = AccountModel.get_by_user_id(current_user['user_id'])
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    balance = AccountModel.get_balance(account['account_id'])
    
    return AccountResponse(
        account_id=account['account_id'],
        balance_pence=balance,
        currency=account['currency']
    )

# Transaction endpoints
@app.post("/deposits", response_model=DepositWithdrawalResponse, status_code=status.HTTP_201_CREATED)
async def create_deposit(
    request: DepositRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a deposit."""
    account = AccountModel.get_by_user_id(current_user['user_id'])
    system_account_id = AccountModel.get_system_account_id()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Create deposit: debit system account, credit user account
    result = TransactionModel.create_transaction(
        transaction_type='deposit',
        debit_account_id=system_account_id,
        credit_account_id=account['account_id'],
        amount_pence=request.amount_pence
    )
    
    balance = AccountModel.get_balance(account['account_id'])
    
    return DepositWithdrawalResponse(
        transaction_id=result['transaction_id'],
        status=result['status'],
        balance_pence=balance
    )

@app.post("/withdrawals", response_model=DepositWithdrawalResponse, status_code=status.HTTP_201_CREATED)
async def create_withdrawal(
    request: WithdrawalRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a withdrawal."""
    account = AccountModel.get_by_user_id(current_user['user_id'])
    system_account_id = AccountModel.get_system_account_id()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Check balance (BR2)
    balance = AccountModel.get_balance(account['account_id'])
    if balance < request.amount_pence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds"
        )
    
    # Check daily limit (BR3)
    daily_total = TransactionModel.get_transfers_withdrawals_last_24h(account['account_id'])
    if daily_total + request.amount_pence > 100000:  # £1,000 in pence
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Daily withdrawal/transfer limit of £1,000 exceeded"
        )
    
    # Create withdrawal: debit user account, credit system account
    result = TransactionModel.create_transaction(
        transaction_type='withdrawal',
        debit_account_id=account['account_id'],
        credit_account_id=system_account_id,
        amount_pence=request.amount_pence
    )
    
    balance = AccountModel.get_balance(account['account_id'])
    
    return DepositWithdrawalResponse(
        transaction_id=result['transaction_id'],
        status=result['status'],
        balance_pence=balance
    )

@app.post("/transfers", response_model=DepositWithdrawalResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    request: TransferRequest,
    current_user: dict = Depends(get_current_user)
):
    """Transfer funds to another user."""
    sender_account = AccountModel.get_by_user_id(current_user['user_id'])
    
    if not sender_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Check self-transfer (BR9)
    if request.recipient_email == current_user['email']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer to your own account"
        )
    
    # Find recipient (BR10)
    recipient_user = UserModel.get_by_email(request.recipient_email)
    if not recipient_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found"
        )
    
    recipient_account = AccountModel.get_by_user_id(recipient_user['user_id'])
    
    # Check balance (BR1)
    sender_balance = AccountModel.get_balance(sender_account['account_id'])
    if sender_balance < request.amount_pence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds"
        )
    
    # Check daily limit (BR3)
    daily_total = TransactionModel.get_transfers_withdrawals_last_24h(sender_account['account_id'])
    if daily_total + request.amount_pence > 100000:  # £1,000 in pence
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Daily withdrawal/transfer limit of £1,000 exceeded"
        )
    
    # Create transfer: debit sender, credit recipient
    result = TransactionModel.create_transaction(
        transaction_type='transfer',
        debit_account_id=sender_account['account_id'],
        credit_account_id=recipient_account['account_id'],
        amount_pence=request.amount_pence
    )
    
    balance = AccountModel.get_balance(sender_account['account_id'])
    
    return DepositWithdrawalResponse(
        transaction_id=result['transaction_id'],
        status=result['status'],
        balance_pence=balance
    )

@app.get("/transactions", response_model=list[TransactionResponse])
async def get_transactions(current_user: dict = Depends(get_current_user)):
    """Get transaction history for the current user."""
    account = AccountModel.get_by_user_id(current_user['user_id'])
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    transactions = TransactionModel.get_user_transactions(account['account_id'])
    
    # Format the response
    formatted_transactions = []
    for tx in transactions:
        # Parse the datetime string to datetime object
        created_at = tx['created_at']
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        formatted_transactions.append({
            "transaction_id": tx['transaction_id'],
            "type": tx['type'],
            "amount_pence": tx['amount_pence'],
            "direction": tx['direction'],
            "status": tx['status'],
            "created_at": created_at
        })
    
    return formatted_transactions

@app.post("/transactions/{transaction_id}/reversal", response_model=ReversalResponse, status_code=status.HTTP_201_CREATED)
async def reverse_transaction(
    transaction_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Reverse a completed transfer."""
    account = AccountModel.get_by_user_id(current_user['user_id'])
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )
    
    # Attempt reversal
    result = TransactionModel.reverse_transfer(transaction_id, account['account_id'])
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reverse this transaction. It may not exist, not be a transfer, already be reversed, or you're not the sender"
        )
    
    return ReversalResponse(
        transaction_id=result['transaction_id'],
        reverses_transaction_id=result['reverses_transaction_id'],
        status=result['status']
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)