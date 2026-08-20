# P2P Payments Wallet

A peer-to-peer payments wallet built with FastAPI + SQLite. All balances are
recorded on a double-entry ledger and derived from ledger entries (never stored
in place). Money is integer pence throughout; no floating point is used.

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`. On first start the tables and
the single internal system account are created automatically. Set a real secret
in production: `export WALLET_SECRET_KEY=...`.

## Test

```bash
pip install httpx            # needed only by the test client
python3 test_e2e.py          # 39 end-to-end checks over every rule
```

## Endpoints

| Method | Path | Auth | Success |
|---|---|---|---|
| POST | `/auth/register` | no | 201 `{user_id, email}` |
| POST | `/auth/login` | no | 200 `{access_token}` |
| GET | `/accounts/me` | yes | 200 `{account_id, balance_pence, currency}` |
| POST | `/deposits` | yes | 201 `{transaction_id, status, balance_pence}` |
| POST | `/withdrawals` | yes | 201 `{transaction_id, status, balance_pence}` |
| POST | `/transfers` | yes | 201 `{transaction_id, status, balance_pence}` |
| GET | `/transactions` | yes | 200 list of `{transaction_id, type, amount_pence, direction, status, created_at}` |
| POST | `/transactions/{id}/reversal` | yes | 201 `{transaction_id, reverses_transaction_id, status}` |

Authenticated endpoints expect `Authorization: Bearer <access_token>`.

## Modules

- `config.py` — constants (secret, limits, currency, DB URL).
- `database.py` — SQLAlchemy engine, session, `Base`, FK pragma.
- `models.py` — `User`, `Account`, `Transaction`, `LedgerEntry`.
- `schemas.py` — request/response bodies; strict integer-pence validation.
- `security.py` — PBKDF2 password hashing (per-user salt) + JWT tokens.
- `ledger.py` — balance derivation, rolling-limit tally, atomic double-entry posting.
- `dependencies.py` — bearer-token → current user.
- `main.py` — FastAPI app and all endpoints.
- `utils.py` — UTC time + ISO serialisation helpers.

## Error responses (non-success)

- `401` missing/invalid/expired token, or wrong login credentials.
- `404` transfer recipient not registered; reversal target not found or not owned by caller.
- `409` email already registered; transaction cannot be reversed (not a transfer, or already reversed).
- `400` business rejection: insufficient funds, self-transfer, daily limit exceeded.
- `422` malformed body / invalid amount (zero, negative, fractional, non-numeric, out of range).

## Design decisions (where the spec left it open)

- **Balances derived, never stored** (BR6): `balance = Σ credits − Σ debits` over an
  account's ledger entries.
- **Ledger sign convention**: credit increases a user's balance, debit decreases it.
  Deposit = debit system / credit user; withdrawal = debit user / credit system;
  transfer = debit sender / credit recipient; reversal = debit recipient / credit sender.
- **Atomicity** (NFR5): each transaction plus its two ledger entries is committed as a
  single unit. A process-wide write lock serialises value-moving operations so
  read-check-write sequences (balance/limit checks) cannot race under SQLite.
- **Daily limit** (BR3): sum of the user's `transfer` + `withdrawal` transaction amounts
  in the rolling 24h window preceding the request, plus the new amount, must be
  ≤ £1,000. Deposits and reversals are excluded. Reversed transfers still count
  toward the window (the value did move when made).
- **Reversal** restores the sender and debits the recipient even if that takes the
  recipient's balance negative — a reversal is a correction and is not gated on the
  recipient's current funds; the spec defines no such check.
- **Privacy**: reversing a transaction that is not yours returns `404` (not `403`) so the
  existence of other users' transactions is not revealed. Login gives the same error
  for unknown email and wrong password. Emails are matched case-insensitively.
- **Amount validation** uses Pydantic strict integers, so JSON floats such as `10.0`
  are rejected as fractional.
