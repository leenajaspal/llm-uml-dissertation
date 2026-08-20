# Simple Payments App

A small FastAPI + SQLite wallet application.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="replace-with-a-long-random-secret"
export DATABASE_PATH="./payments.sqlite3"
uvicorn app.main:app --reload
```

FastAPI documentation routes are disabled so the application only exposes the required API paths.

## Endpoints

- `POST /auth/register`
- `POST /auth/login`
- `GET /accounts/me`
- `POST /deposits`
- `POST /withdrawals`
- `POST /transfers`
- `GET /transactions`
- `POST /transactions/{transaction_id}/reversal`

Authenticated endpoints require `Authorization: Bearer <access_token>`.

All monetary values are integer pence. The default daily money-out limit is `100000` pence (£1000), configurable with `DAILY_MOVE_LIMIT_PENCE`.
