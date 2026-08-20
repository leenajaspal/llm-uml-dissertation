"""FastAPI application implementing a peer-to-peer payments wallet.

All monetary values are integer pence. No floating point is used for money.
The ledger is double-entry: every transaction produces exactly one debit and
one credit of equal value on two different accounts, so the system-wide sum of
ledger entries is always zero.
"""
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

import auth
from database import get_db, get_system_account_id, init_db

import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

import auth
from database import get_db, get_system_account_id, init_db

# ---------------------------------------------------------------------------
# Configuration / constants
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DAILY_LIMIT_PENCE = 100_000            # £1,000 in pence (BR3)
MAX_AMOUNT_PENCE = 2**63 - 1           # SQLite INTEGER upper bound (NFR4)
PASSWORD_MIN_LEN = 8


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="P2P Payments Wallet", lifespan=lifespan)
security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not isinstance(v, str) or not EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not isinstance(v, str) or len(v) < PASSWORD_MIN_LEN:
            raise ValueError(f"password must be at least {PASSWORD_MIN_LEN} characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


def _validate_amount(v) -> int:
    # Pydantic will reject non-ints (and bools) but be explicit about range/sign.
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValueError("amount_pence must be an integer")
    if v <= 0:
        raise ValueError("amount_pence must be a positive whole number")
    if v > MAX_AMOUNT_PENCE:
        raise ValueError("amount_pence out of representable range")
    return v


class AmountRequest(BaseModel):
    amount_pence: int

    @field_validator("amount_pence")
    @classmethod
    def _va(cls, v):
        return _validate_amount(v)


class TransferRequest(BaseModel):
    recipient_email: str
    amount_pence: int

    @field_validator("recipient_email")
    @classmethod
    def _validate_recipient(cls, v: str) -> str:
        if not isinstance(v, str) or not EMAIL_RE.match(v):
            raise ValueError("invalid recipient email")
        return v.strip().lower()

    @field_validator("amount_pence")
    @classmethod
    def _va(cls, v):
        return _validate_amount(v)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------
class RegisterResponse(BaseModel):
    user_id: int
    email: str


class LoginResponse(BaseModel):
    access_token: str


class AccountResponse(BaseModel):
    account_id: int
    balance_pence: int
    currency: str


class TransactionResponse(BaseModel):
    transaction_id: int
    status: str
    balance_pence: int


class TransactionHistoryItem(BaseModel):
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


# ---------------------------------------------------------------------------
# Authentication dependency
# ---------------------------------------------------------------------------
def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if creds is None or (creds.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = auth.decode_access_token(creds.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        account = conn.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND is_system = 0",
            (user_id,),
        ).fetchone()
    if account is None:
        raise HTTPException(status_code=401, detail="Account not found")
    return {"user_id": user["id"], "email": user["email"], "account_id": account["id"]}


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_balance(conn, account_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(
            SUM(CASE WHEN direction='credit' THEN amount_pence ELSE -amount_pence END),
            0
        ) AS balance
        FROM ledger_entries WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return int(row["balance"])


def record_transaction(
    conn,
    txn_type: str,
    entries: list,
    reverses_id: Optional[int] = None,
) -> int:
    """Insert a transaction and its (exactly two) ledger entries atomically.

    `entries` is a list of (account_id, amount_pence, direction) tuples and
    must contain exactly one debit and one credit of equal value on two
    different accounts (BR4).
    """
    if len(entries) != 2:
        raise ValueError("a transaction must have exactly two ledger entries")
    debits = [e for e in entries if e[2] == "debit"]
    credits = [e for e in entries if e[2] == "credit"]
    if len(debits) != 1 or len(credits) != 1:
        raise ValueError("a transaction must have one debit and one credit")
    if debits[0][1] != credits[0][1]:
        raise ValueError("debit and credit must be of equal value")
    if debits[0][0] == credits[0][0]:
        raise ValueError("debit and credit must be against different accounts")

    now = _now_iso()
    cur = conn.execute(
        "INSERT INTO transactions (type, status, reverses_transaction_id, created_at) "
        "VALUES (?, 'completed', ?, ?)",
        (txn_type, reverses_id, now),
    )
    txn_id = cur.lastrowid
    for account_id, amount, direction in entries:
        conn.execute(
            "INSERT INTO ledger_entries "
            "(transaction_id, account_id, amount_pence, direction, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (txn_id, account_id, amount, direction, now),
        )
    return txn_id


def check_daily_limit(conn, account_id: int, new_amount: int) -> bool:
    """BR3: combined transfers+withdrawals made by the user in the last 24h
    must not exceed £1,000. The new requested amount is included in the check.
    Reversed transfers still count (they were 'made').
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(le.amount_pence), 0) AS total
        FROM ledger_entries le
        JOIN transactions t ON le.transaction_id = t.id
        WHERE le.account_id = ?
          AND le.direction = 'debit'
          AND t.type IN ('withdrawal', 'transfer')
          AND t.created_at >= ?
        """,
        (account_id, cutoff),
    ).fetchone()
    current = int(row["total"])
    return (current + new_amount) <= DAILY_LIMIT_PENCE


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/auth/register", response_model=RegisterResponse, status_code=201)
def register(req: RegisterRequest):
    pw_hash, salt = auth.hash_password(req.password)
    now = _now_iso()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? COLL NOCASE", (req.email,)
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="email already registered")
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, password_salt, created_at) "
            "VALUES (?, ?, ?, ?)",
            (req.email, pw_hash, salt, now),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO accounts (user_id, currency, is_system, created_at) "
            "VALUES (?, 'GBP', 0, ?)",
            (user_id, now),
        )
    return RegisterResponse(user_id=user_id, email=req.email)


@app.post("/auth/login", response_model=LoginResponse, status_code=200)
def login(req: LoginRequest):
    email = req.email.strip().lower() if isinstance(req.email, str) else ""
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, password_salt FROM users "
            "WHERE email = ? COLL NOCASE",
            (email,),
        ).fetchone()
    if user is None or not auth.verify_password(
        req.password, user["password_hash"], user["password_salt"]
    ):
        # Same error for unknown user / wrong password to avoid user enumeration.
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = auth.create_access_token(user["id"])
    return LoginResponse(access_token=token)


@app.get("/accounts/me", response_model=AccountResponse, status_code=200)
def get_my_account(current=Depends(get_current_user)):
    with get_db() as conn:
        account = conn.execute(
            "SELECT id, currency FROM accounts WHERE id = ?",
            (current["account_id"],),
        ).fetchone()
        if account is None:
            raise HTTPException(status_code=404, detail="account not found")
        balance = get_balance(conn, current["account_id"])
    return AccountResponse(
        account_id=account["id"],
        balance_pence=balance,
        currency=account["currency"],
    )


@app.post("/deposits", response_model=TransactionResponse, status_code=201)
def deposit(req: AmountRequest, current=Depends(get_current_user)):
    with get_db() as conn:
        system_id = get_system_account_id(conn)
        txn_id = record_transaction(
            conn,
            "deposit",
            [
                (system_id, req.amount_pence, "debit"),       # BR5
                (current["account_id"], req.amount_pence, "credit"),
            ],
        )
        balance = get_balance(conn, current["account_id"])
    return TransactionResponse(
        transaction_id=txn_id, status="completed", balance_pence=balance
    )


@app.post("/withdrawals", response_model=TransactionResponse, status_code=201)
def withdraw(req: AmountRequest, current=Depends(get_current_user)):
    with get_db() as conn:
        balance = get_balance(conn, current["account_id"])
        if balance < req.amount_pence:                                  # BR2
            raise HTTPException(status_code=422, detail="insufficient balance")
        if not check_daily_limit(conn, current["account_id"], req.amount_pence):  # BR3
            raise HTTPException(status_code=422, detail="daily limit exceeded")
        system_id = get_system_account_id(conn)
        txn_id = record_transaction(
            conn,
            "withdrawal",
            [
                (current["account_id"], req.amount_pence, "debit"),    # BR5
                (system_id, req.amount_pence, "credit"),
            ],
        )
        balance = get_balance(conn, current["account_id"])
    return TransactionResponse(
        transaction_id=txn_id, status="completed", balance_pence=balance
    )


@app.post("/transfers", response_model=TransactionResponse, status_code=201)
def transfer(req: TransferRequest, current=Depends(get_current_user)):
    with get_db() as conn:
        recipient_user = conn.execute(
            "SELECT id FROM users WHERE email = ? COLL NOCASE",
            (req.recipient_email,),
        ).fetchone()
        if recipient_user is None:                                      # BR10
            raise HTTPException(status_code=404, detail="recipient not found")
        if recipient_user["id"] == current["user_id"]:                  # BR9
            raise HTTPException(status_code=422, detail="cannot transfer to your own account")
        recipient_account = conn.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND is_system = 0",
            (recipient_user["id"],),
        ).fetchone()
        if recipient_account is None:
            raise HTTPException(status_code=404, detail="recipient account not found")

        balance = get_balance(conn, current["account_id"])
        if balance < req.amount_pence:                                  # BR1
            raise HTTPException(status_code=422, detail="insufficient balance")
        if not check_daily_limit(conn, current["account_id"], req.amount_pence):  # BR3
            raise HTTPException(status_code=422, detail="daily limit exceeded")

        txn_id = record_transaction(
            conn,
            "transfer",
            [
                (current["account_id"], req.amount_pence, "debit"),
                (recipient_account["id"], req.amount_pence, "credit"),
            ],
        )
        balance = get_balance(conn, current["account_id"])
    return TransactionResponse(
        transaction_id=txn_id, status="completed", balance_pence=balance
    )


@app.get("/transactions", response_model=List[TransactionHistoryItem], status_code=200)
def list_transactions(current=Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.id   AS transaction_id,
                   t.type AS type,
                   le.amount_pence AS amount_pence,
                   le.direction    AS direction,
                   t.status        AS status,
                   t.created_at    AS created_at
            FROM transactions t
            JOIN ledger_entries le ON le.transaction_id = t.id
            WHERE le.account_id = ?
            ORDER BY t.created_at DESC, t.id DESC
            """,
            (current["account_id"],),
        ).fetchall()
    return [
        TransactionHistoryItem(
            transaction_id=r["transaction_id"],
            type=r["type"],
            amount_pence=r["amount_pence"],
            direction=r["direction"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@app.post(
    "/transactions/{transaction_id}/reversal",
    response_model=ReversalResponse,
    status_code=201,
)
def reverse_transfer(transaction_id: int, current=Depends(get_current_user)):
    with get_db() as conn:
        txn = conn.execute(
            "SELECT id, type, status FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        if txn is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        if txn["type"] != "transfer":                                   # BR8
            raise HTTPException(
                status_code=422, detail="only transfers can be reversed"
            )
        if txn["status"] != "completed":                                # BR8
            raise HTTPException(
                status_code=422, detail="transaction is not reversible"
            )

        entries = conn.execute(
            "SELECT account_id, amount_pence, direction FROM ledger_entries "
            "WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchall()

        user_entry = None
        other_entry = None
        for e in entries:
            if e["account_id"] == current["account_id"]:
                user_entry = e
            else:
                other_entry = e

        # FR8 / NFR3: only the sending party may reverse.
        if user_entry is None:
            raise HTTPException(
                status_code=403, detail="you were not a party to this transaction"
            )
        if user_entry["direction"] != "debit":
            raise HTTPException(
                status_code=403, detail="only the sender can reverse a transfer"
            )
        if other_entry is None:
            # Should be impossible for a well-formed transfer.
            raise HTTPException(status_code=500, detail="malformed transaction")

        amount = user_entry["amount_pence"]
        # BR7: opposite-direction entries; original marked reversed; nothing deleted/amended.
        new_txn_id = record_transaction(
            conn,
            "reversal",
            [
                (user_entry["account_id"], amount, "credit"),
                (other_entry["account_id"], amount, "debit"),
            ],
            reverses_id=transaction_id,
        )
        conn.execute(
            "UPDATE transactions SET status = 'reversed' WHERE id = ?",
            (transaction_id,),
        )

    return ReversalResponse(
        transaction_id=new_txn_id,
        reverses_transaction_id=transaction_id,
        status="completed",
    )


# ---------------------------------------------------------------------------
# Run directly: `python main.py`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.environ.get("WALLET_HOST", "127.0.0.1"),
        port=int(os.environ.get("WALLET_PORT", "8000")),
        reload=False,
    )