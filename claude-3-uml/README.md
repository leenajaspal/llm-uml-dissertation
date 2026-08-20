# Payments Wallet

A peer-to-peer payments wallet built with **FastAPI** and **SQLite**. All
balances are recorded on a **double-entry ledger**; account balances are always
derived from ledger entries and never stored as a mutable field. Every monetary
value is an integer number of **pence**.

## Layout

```
app/
  config.py     configuration constants (limits, currency, secret, DB path)
  db.py         SQLite connection, schema, atomic write transactions, system account
  security.py   PBKDF2 password hashing + signed bearer tokens
  schemas.py    Pydantic request/response models (strict money validation)
  ledger.py     double-entry ledger + deposit/withdraw/transfer/reverse logic
  main.py       FastAPI app: routes, auth dependency, error handling
requirements.txt
smoke_test.py   end-to-end test of every endpoint and business rule
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # optional
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is then at `http://127.0.0.1:8000` (interactive docs at `/docs`).
Set `WALLET_SECRET` in the environment for anything other than local testing;
optionally set `WALLET_DB_PATH` to relocate the database file.

## Test

```bash
pip install httpx      # only needed for the test client
python smoke_test.py
```

## Endpoints

| Method & path                                   | Auth | Success |
|-------------------------------------------------|------|---------|
| `POST /auth/register`                           | no   | 201     |
| `POST /auth/login`                              | no   | 200     |
| `GET  /accounts/me`                             | yes  | 200     |
| `POST /deposits`                                | yes  | 201     |
| `POST /withdrawals`                             | yes  | 201     |
| `POST /transfers`                               | yes  | 201     |
| `GET  /transactions`                            | yes  | 200     |
| `POST /transactions/{transaction_id}/reversal`  | yes  | 201     |

Authenticated endpoints expect `Authorization: Bearer <access_token>`.

### Error responses

Bodies for errors are `{"detail": "..."}`.

* **422** – body fails validation, or the amount is rejected by a business rule
  (insufficient funds, daily limit exceeded, self-transfer). No account changes.
* **401** – missing / invalid / expired token, or bad login credentials.
* **403** – authenticated, but trying to reverse a transfer you did not send.
* **404** – unknown transfer recipient, or a transaction you cannot see.
* **409** – registering an existing email, or reversing something that is not a
  reversible completed transfer.

## Design decisions

* **Money** is integer pence everywhere; floating point is never used. Amounts
  are validated strictly, so `0`, negatives, `10.5`, `"100"` and booleans are
  all rejected before any account is touched (BR11, NFR4).
* **Balances** are derived as `sum(credits) − sum(debits)` over an account's
  ledger entries (BR6). Deposits credit the user / debit the system account;
  withdrawals do the reverse (BR5). Transfers debit the sender / credit the
  recipient. The signed sum of *all* ledger entries is therefore always 0 (BR4).
* **Atomicity & races.** Each mutating operation runs inside a single
  `BEGIN IMMEDIATE` transaction. IMMEDIATE takes the write-lock up front, which
  serialises writers so the read-then-write balance/limit checks cannot be raced
  (prevents double-spends and double-reversals) and guarantees no partial
  records (NFR5).
* **Daily limit (BR3).** Outgoing transfers and withdrawals are summed over the
  rolling 24-hour window ending at the moment of the request; deposits are
  excluded. A reversed transfer still counts toward the window it occurred in —
  the limit caps value sent out, and a later correction does not restore that
  day's allowance.
* **Reversals (BR7/BR8).** A reversal is a *new* `reversal` transaction whose
  entries move the original value in the opposite direction; the original is
  marked `reversed` and is otherwise untouched. Only a completed transfer, sent
  by the caller, can be reversed, and only once. A reversal is applied
  unconditionally (the spec sets no recipient-balance condition), so a clawback
  can leave the recipient with a negative balance — subsequent withdrawals and
  transfers by that recipient are still checked against their balance.
* **Passwords (NFR1)** are stored as PBKDF2-HMAC-SHA256 with a per-user random
  salt; the plaintext is never stored, logged or returned.
* **Isolation (NFR3).** Every authenticated action resolves the account from the
  token alone. There is no account/user identifier in any path or body that
  could be used to reach another user's data; the only path parameter is a
  `transaction_id`, which is checked for visibility and ownership.
