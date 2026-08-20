# Peer-to-peer payments wallet

A FastAPI + SQLite backend implementing the specified wallet API.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn wallet_app.main:app --reload
```

By default the SQLite database is created at `wallet.sqlite3` in the current working directory. To use a different path:

```bash
export WALLET_DATABASE_URL=/path/to/wallet.sqlite3
uvicorn wallet_app.main:app --reload
```

## Authentication

Use `POST /auth/login` to get an `access_token`, then send it as:

```http
Authorization: Bearer <access_token>
```

The app intentionally disables FastAPI's automatic `/docs`, `/redoc`, and `/openapi.json` routes so that only the required endpoints are exposed.
