"""Peer-to-peer payments wallet API.

A registered user holds exactly one GBP account, may deposit, withdraw,
transfer to another user, view their own transaction history, and reverse a
transfer they sent. All balances are recorded on a double-entry ledger and
derived from ledger entries (never stored in place).

Error model (successful responses are defined by the specification):
  * 401 - missing/invalid/expired credential
  * 404 - transfer recipient not registered; reversal target not found or not
          owned by the caller
  * 409 - email already registered; transaction cannot be reversed
          (not a transfer, or not currently completed)
  * 400 - business rejection (insufficient funds, self-transfer, daily limit)
  * 422 - malformed body / invalid monetary amount (FastAPI validation)
"""
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import CURRENCY, DAILY_LIMIT_PENCE
from database import Base, SessionLocal, engine, get_db
from dependencies import get_current_user
from ledger import (
    account_balance,
    get_system_account,
    get_user_account,
    post_transaction,
    spent_last_24h,
)
from models import (
    DIR_CREDIT,
    DIR_DEBIT,
    STATUS_COMPLETED,
    STATUS_REVERSED,
    TX_DEPOSIT,
    TX_REVERSAL,
    TX_TRANSFER,
    TX_WITHDRAWAL,
    Account,
    LedgerEntry,
    Transaction,
    User,
)
from schemas import (
    AccountResponse,
    AmountRequest,
    LoginRequest,
    LoginResponse,
    MovementResponse,
    RegisterRequest,
    RegisterResponse,
    ReversalResponse,
    TransactionList,
    TransactionListItem,
    TransferRequest,
)
from security import create_access_token, hash_password, verify_password
from utils import to_iso_utc, utcnow

# Serialises all value-moving operations. SQLite offers no row-level locking,
# so a single process-wide lock keeps every read-check-write sequence atomic
# and prevents balance/limit checks from racing concurrent writers (NFR5).
write_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and ensure the single system account exists on startup."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if get_system_account(db) is None:
            db.add(
                Account(
                    user_id=None,
                    currency=CURRENCY,
                    is_system=True,
                    created_at=utcnow(),
                )
            )
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="P2P Payments Wallet", version="1.0.0", lifespan=lifespan)


def _normalise_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """FR1: create one user and one account for a new email address."""
    email = _normalise_email(body.email)
    salt_hex, hash_hex = hash_password(body.password)

    with write_lock:
        if db.query(User).filter(User.email == email).first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        user = User(
            email=email,
            password_hash=hash_hex,
            password_salt=salt_hex,
            created_at=utcnow(),
        )
        db.add(user)
        try:
            db.flush()
            db.add(
                Account(
                    user_id=user.id,
                    currency=CURRENCY,
                    is_system=False,
                    created_at=utcnow(),
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        user_id = user.id

    return RegisterResponse(user_id=user_id, email=email)


@app.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """FR2: authenticate and issue a bearer token."""
    email = _normalise_email(body.email)
    user = db.query(User).filter(User.email == email).first()

    # Same response whether the email is unknown or the password is wrong, so
    # account existence is not leaked.
    if user is None or not verify_password(
        body.password, user.password_salt, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return LoginResponse(access_token=create_access_token(user.id))


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
@app.get("/accounts/me", response_model=AccountResponse)
def get_my_account(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """FR3: retrieve the caller's own balance."""
    account = get_user_account(db, user.id)
    if account is None:
        # Should not happen: an account is created at registration.
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse(
        account_id=account.id,
        balance_pence=account_balance(db, account.id),
        currency=account.currency,
    )


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------
@app.post(
    "/deposits",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def deposit(
    body: AmountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR4: deposit into the caller's account.

    BR5: debit the system account, credit the user's account. Deposits are
    treated as authorised elsewhere and do not count toward the daily limit.
    """
    account = get_user_account(db, user.id)
    system = get_system_account(db)

    with write_lock:
        tx = post_transaction(
            db,
            tx_type=TX_DEPOSIT,
            amount=body.amount_pence,
            debit_account_id=system.id,
            credit_account_id=account.id,
            initiating_user_id=user.id,
            created_at=utcnow(),
        )
        db.commit()
        tx_id, tx_status = tx.id, tx.status
        balance = account_balance(db, account.id)

    return MovementResponse(
        transaction_id=tx_id, status=tx_status, balance_pence=balance
    )


# ---------------------------------------------------------------------------
# Withdrawals
# ---------------------------------------------------------------------------
@app.post(
    "/withdrawals",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def withdraw(
    body: AmountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR5: withdraw from the caller's account.

    BR2: reject if balance < amount. BR3: enforce the rolling daily limit.
    BR5: debit the user's account, credit the system account.
    """
    account = get_user_account(db, user.id)
    system = get_system_account(db)
    amount = body.amount_pence

    with write_lock:
        balance = account_balance(db, account.id)
        if balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")

        now = utcnow()
        if spent_last_24h(db, user.id, now) + amount > DAILY_LIMIT_PENCE:
            raise HTTPException(
                status_code=400,
                detail="Daily transfer/withdrawal limit exceeded",
            )

        tx = post_transaction(
            db,
            tx_type=TX_WITHDRAWAL,
            amount=amount,
            debit_account_id=account.id,
            credit_account_id=system.id,
            initiating_user_id=user.id,
            created_at=now,
        )
        db.commit()
        tx_id, tx_status = tx.id, tx.status
        new_balance = account_balance(db, account.id)

    return MovementResponse(
        transaction_id=tx_id, status=tx_status, balance_pence=new_balance
    )


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------
@app.post(
    "/transfers",
    response_model=MovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def transfer(
    body: TransferRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR6: transfer to another registered user by email.

    BR10: recipient must be a registered user. BR9: no self-transfer.
    BR1: reject if balance < amount. BR3: enforce the rolling daily limit.
    """
    recipient_email = _normalise_email(body.recipient_email)
    amount = body.amount_pence

    recipient = db.query(User).filter(User.email == recipient_email).first()
    if recipient is None:
        raise HTTPException(
            status_code=404, detail="Recipient is not a registered user"
        )
    if recipient.id == user.id:
        raise HTTPException(
            status_code=400, detail="Cannot transfer to your own account"
        )

    sender_account = get_user_account(db, user.id)
    recipient_account = get_user_account(db, recipient.id)
    if recipient_account is None:
        raise HTTPException(
            status_code=404, detail="Recipient is not a registered user"
        )

    with write_lock:
        balance = account_balance(db, sender_account.id)
        if balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")

        now = utcnow()
        if spent_last_24h(db, user.id, now) + amount > DAILY_LIMIT_PENCE:
            raise HTTPException(
                status_code=400,
                detail="Daily transfer/withdrawal limit exceeded",
            )

        tx = post_transaction(
            db,
            tx_type=TX_TRANSFER,
            amount=amount,
            debit_account_id=sender_account.id,
            credit_account_id=recipient_account.id,
            initiating_user_id=user.id,
            created_at=now,
        )
        db.commit()
        tx_id, tx_status = tx.id, tx.status
        new_balance = account_balance(db, sender_account.id)

    return MovementResponse(
        transaction_id=tx_id, status=tx_status, balance_pence=new_balance
    )


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------
@app.get("/transactions", response_model=TransactionList)
def list_transactions(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """FR7: list the transactions touching the caller's own account.

    ``direction`` is reported from the perspective of the user's account: the
    direction of that account's ledger entry within each transaction.
    """
    account = get_user_account(db, user.id)

    # Each transaction touches the user's account through exactly one entry
    # (the other entry is against a different account), so this map is 1:1.
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.account_id == account.id)
        .all()
    )
    direction_by_tx = {e.transaction_id: e.direction for e in entries}
    if not direction_by_tx:
        return []

    transactions = (
        db.query(Transaction)
        .filter(Transaction.id.in_(list(direction_by_tx.keys())))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .all()
    )

    return [
        TransactionListItem(
            transaction_id=tx.id,
            type=tx.type,
            amount_pence=tx.amount_pence,
            direction=direction_by_tx[tx.id],
            status=tx.status,
            created_at=to_iso_utc(tx.created_at),
        )
        for tx in transactions
    ]


# ---------------------------------------------------------------------------
# Reversal
# ---------------------------------------------------------------------------
@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR8: reverse a completed transfer the caller sent.

    BR8: only a completed transfer may be reversed, and only once. BR7: a new
    reversal transaction is created moving the value the opposite way; the
    original is marked reversed; nothing existing is deleted or amended.
    """
    with write_lock:
        original = db.get(Transaction, transaction_id)

        # Not found, or not initiated by this user -> 404 (do not reveal that a
        # transaction belonging to someone else exists). Only the sending party
        # of a transfer is its initiator.
        if original is None or original.initiating_user_id != user.id:
            raise HTTPException(status_code=404, detail="Transaction not found")

        if original.type != TX_TRANSFER:
            raise HTTPException(
                status_code=409,
                detail="Only transfers can be reversed",
            )
        if original.status != STATUS_COMPLETED:
            raise HTTPException(
                status_code=409,
                detail="Transaction has already been reversed",
            )

        # Original transfer entries: debit = sender account, credit = recipient.
        debit_entry = (
            db.query(LedgerEntry)
            .filter(
                LedgerEntry.transaction_id == original.id,
                LedgerEntry.direction == DIR_DEBIT,
            )
            .first()
        )
        credit_entry = (
            db.query(LedgerEntry)
            .filter(
                LedgerEntry.transaction_id == original.id,
                LedgerEntry.direction == DIR_CREDIT,
            )
            .first()
        )

        # Reversal moves value the opposite way: debit the recipient, credit
        # the sender.
        reversal = post_transaction(
            db,
            tx_type=TX_REVERSAL,
            amount=original.amount_pence,
            debit_account_id=credit_entry.account_id,
            credit_account_id=debit_entry.account_id,
            initiating_user_id=user.id,
            created_at=utcnow(),
            reverses_transaction_id=original.id,
        )
        original.status = STATUS_REVERSED
        db.commit()
        reversal_id, reversal_status = reversal.id, reversal.status

    return ReversalResponse(
        transaction_id=reversal_id,
        reverses_transaction_id=transaction_id,
        status=reversal_status,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
