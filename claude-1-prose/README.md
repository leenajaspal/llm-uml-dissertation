# Payments App

A minimal wallet/payments backend: register, log in, hold a balance, deposit,
withdraw, send money to other users by email, view your own history, and
reverse a payment. Built with **FastAPI** + **SQLite**, standard/widely‑available
libraries only, no external payment service.

All monetary values are **integer pence**.

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`. Run the tests with
`python test_smoke.py` (56 end‑to‑end checks, uses a throwaway database).

## Endpoints

| Method & path | Auth | Success |
|---|---|---|
| `POST /auth/register` | – | 201 `{user_id, email}` |
| `POST /auth/login` | – | 200 `{access_token}` |
| `GET /accounts/me` | Bearer | 200 `{account_id, balance_pence, currency}` |
| `POST /deposits` | Bearer | 201 `{transaction_id, status, balance_pence}` |
| `POST /withdrawals` | Bearer | 201 `{transaction_id, status, balance_pence}` |
| `POST /transfers` | Bearer | 201 `{transaction_id, status, balance_pence}` |
| `GET /transactions` | Bearer | 200 `[{transaction_id, type, amount_pence, direction, status, created_at}]` |
| `POST /transactions/{id}/reversal` | Bearer | 201 `{transaction_id, reverses_transaction_id, status}` |

Authenticated endpoints expect `Authorization: Bearer <access_token>`.

## How money correctness is guaranteed

* **Double-entry ledger.** Balances are never stored as a mutable number. An
  account's balance is the `SUM` of its immutable `ledger_entries`. History is
  the single source of truth, so a balance can never disagree with what
  happened on the account.
* **Every transaction balances to zero.** Deposits/withdrawals use a hidden
  `system` account as counterparty; transfers move between two user accounts.
  The grand total of all ledger entries is therefore always exactly `0` — money
  cannot be created, lost or double-counted. (`verify_ledger_integrity()`
  asserts this; the test suite checks it after every operation, including a
  50-thread concurrency stress test.)
* **Serialised writes.** Each money operation runs in a `BEGIN IMMEDIATE`
  transaction, so the check-then-write (funds/cap/ownership) is atomic and
  concurrent writers cannot overdraw an account. WAL mode keeps reads
  non-blocking.

## Decisions made (the spec left these open)

* **Errors:** `401` auth failures, `403` acting on someone else's resource,
  `404` unknown recipient/transaction, `409` business conflicts (insufficient
  funds, daily cap, duplicate email, already/again reversed, reversal would
  overdraw), `422` schema validation. Bodies are `{"detail": "..."}`.
* **Daily cap (£1000):** applies to money moving *out* per UTC day
  (withdrawals + transfers sent), matching its stated purpose of limiting
  takeover damage. Deposits, received transfers and reversals do not count; a
  reversed transaction frees up its allowance again.
* **Statuses:** new deposit/withdrawal/transfer → `completed`; a reversed
  original → `reversed`; a reversal itself → `completed`. `direction` is from
  the viewer's perspective: `credit` (money in) or `debit` (money out).
* **Reversal:** only the *initiator* of a transaction may reverse it, once. A
  reversal cannot be reversed. If the funds have already moved on and a
  reversal would push a user account negative, it is refused (`409`) rather than
  creating a negative balance.
* **Security:** passwords hashed with PBKDF2-HMAC-SHA256 (per-user salt,
  200k iterations, constant-time verify); JWT access tokens (HS256, pinned
  algorithm, 24h expiry); login is constant-time and generic to avoid user
  enumeration; users only ever see transactions their own account took part in.
* **Emails** are treated case-insensitively.
