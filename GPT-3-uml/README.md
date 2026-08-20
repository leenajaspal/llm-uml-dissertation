# Payments Wallet FastAPI Application

A complete FastAPI + SQLite peer-to-peer wallet implementation using a double-entry ledger.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The default SQLite database file is `wallet.db` in the working directory. Override it with:

```bash
export DATABASE_URL="sqlite:///./another-file.db"
```

## Authentication

Register and log in first. Use the returned token on protected endpoints:

```http
Authorization: Bearer <access_token>
```

All money amounts are integer pence. The application supports GBP only.
