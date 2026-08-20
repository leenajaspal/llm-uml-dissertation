from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import get_current_user, hash_password, issue_access_token, verify_password
from .database import Base, SessionLocal, engine, get_db
from .ledger import (
    SYSTEM_ACCOUNT_ID,
    assert_transaction_has_balanced_entries,
    create_double_entry_transaction,
    enforce_daily_outgoing_limit,
    ensure_system_account,
    get_balance_pence,
    get_user_account,
)
from .models import Account, LedgerEntry, Transaction, User
from .schemas import (
    AccountMeResponse,
    AmountRequest,
    LoginRequest,
    LoginResponse,
    MoneyMovementResponse,
    RegisterRequest,
    RegisterResponse,
    ReversalResponse,
    TransactionHistoryItem,
    TransferRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_system_account(db)
    yield


app = FastAPI(
    title="Payments Wallet",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> RegisterResponse:
    password_hash, password_salt = hash_password(payload.password)
    user = User(
        email=payload.email,
        password_hash=password_hash,
        password_salt=password_salt,
    )
    account = Account(user=user, currency="GBP", is_system=False)

    try:
        db.add(user)
        db.add(account)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
        )

    return RegisterResponse(user_id=user.user_id, email=user.email)


@app.post("/auth/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_salt, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = issue_access_token(db, user)
    db.commit()
    return LoginResponse(access_token=access_token)


@app.get("/accounts/me", response_model=AccountMeResponse, status_code=status.HTTP_200_OK)
def get_my_account(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AccountMeResponse:
    account = get_user_account(db, current_user.user_id)
    return AccountMeResponse(
        account_id=account.account_id,
        balance_pence=get_balance_pence(db, account.account_id),
        currency=account.currency,
    )


@app.post("/deposits", response_model=MoneyMovementResponse, status_code=status.HTTP_201_CREATED)
def deposit(
    payload: AmountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MoneyMovementResponse:
    account = get_user_account(db, current_user.user_id)

    try:
        transaction = create_double_entry_transaction(
            db=db,
            transaction_type="deposit",
            debit_account_id=SYSTEM_ACCOUNT_ID,
            credit_account_id=account.account_id,
            amount_pence=payload.amount_pence,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return MoneyMovementResponse(
        transaction_id=transaction.transaction_id,
        status=transaction.status,
        balance_pence=get_balance_pence(db, account.account_id),
    )


@app.post("/withdrawals", response_model=MoneyMovementResponse, status_code=status.HTTP_201_CREATED)
def withdraw(
    payload: AmountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MoneyMovementResponse:
    account = get_user_account(db, current_user.user_id)
    amount = payload.amount_pence

    if get_balance_pence(db, account.account_id) < amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    enforce_daily_outgoing_limit(db, account.account_id, amount)

    try:
        transaction = create_double_entry_transaction(
            db=db,
            transaction_type="withdrawal",
            debit_account_id=account.account_id,
            credit_account_id=SYSTEM_ACCOUNT_ID,
            amount_pence=amount,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return MoneyMovementResponse(
        transaction_id=transaction.transaction_id,
        status=transaction.status,
        balance_pence=get_balance_pence(db, account.account_id),
    )


@app.post("/transfers", response_model=MoneyMovementResponse, status_code=status.HTTP_201_CREATED)
def transfer(
    payload: TransferRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MoneyMovementResponse:
    sender_account = get_user_account(db, current_user.user_id)

    recipient = db.scalar(select(User).where(User.email == payload.recipient_email))
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown recipient")

    if recipient.user_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer to your own account",
        )

    recipient_account = get_user_account(db, recipient.user_id)
    amount = payload.amount_pence

    if get_balance_pence(db, sender_account.account_id) < amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    enforce_daily_outgoing_limit(db, sender_account.account_id, amount)

    try:
        transaction = create_double_entry_transaction(
            db=db,
            transaction_type="transfer",
            debit_account_id=sender_account.account_id,
            credit_account_id=recipient_account.account_id,
            amount_pence=amount,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return MoneyMovementResponse(
        transaction_id=transaction.transaction_id,
        status=transaction.status,
        balance_pence=get_balance_pence(db, sender_account.account_id),
    )


@app.get(
    "/transactions",
    response_model=list[TransactionHistoryItem],
    status_code=status.HTTP_200_OK,
)
def list_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TransactionHistoryItem]:
    account = get_user_account(db, current_user.user_id)
    rows = db.execute(
        select(Transaction, LedgerEntry)
        .join(LedgerEntry, LedgerEntry.transaction_id == Transaction.transaction_id)
        .where(LedgerEntry.account_id == account.account_id)
        .order_by(Transaction.created_at.desc(), Transaction.transaction_id.desc())
    ).all()

    return [
        TransactionHistoryItem(
            transaction_id=transaction.transaction_id,
            type=transaction.type,
            amount_pence=ledger_entry.amount_pence,
            direction=ledger_entry.direction,
            status=transaction.status,
            created_at=transaction.created_at,
        )
        for transaction, ledger_entry in rows
    ]


@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_transfer(
    transaction_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReversalResponse:
    account = get_user_account(db, current_user.user_id)
    original = db.get(Transaction, transaction_id)

    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    original_entries = db.scalars(
        select(LedgerEntry).where(LedgerEntry.transaction_id == original.transaction_id)
    ).all()
    assert_transaction_has_balanced_entries(original_entries)

    if not any(entry.account_id == account.account_id for entry in original_entries):
        # Returning 404 avoids revealing whether another user's transaction ID exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if original.type != "transfer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only transfers can be reversed",
        )

    sender_entry = next(
        (
            entry
            for entry in original_entries
            if entry.account_id == account.account_id and entry.direction == "debit"
        ),
        None,
    )
    if sender_entry is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the sending party can reverse a transfer",
        )

    existing_reversal = db.scalar(
        select(Transaction).where(Transaction.reverses_transaction_id == original.transaction_id)
    )
    if existing_reversal is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction has already been reversed",
        )

    if original.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction is not a completed transfer",
        )

    recipient_entry = next(entry for entry in original_entries if entry.direction == "credit")

    try:
        reversal = create_double_entry_transaction(
            db=db,
            transaction_type="reversal",
            debit_account_id=recipient_entry.account_id,
            credit_account_id=sender_entry.account_id,
            amount_pence=sender_entry.amount_pence,
            reverses_transaction_id=original.transaction_id,
        )
        original.status = "reversed"
        db.commit()
    except Exception:
        db.rollback()
        raise

    return ReversalResponse(
        transaction_id=reversal.transaction_id,
        reverses_transaction_id=original.transaction_id,
        status=reversal.status,
    )
