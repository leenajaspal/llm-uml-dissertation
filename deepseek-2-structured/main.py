from fastapi import FastAPI
from database import engine, Base
from routers import auth_router, accounts_router, deposits_router, withdrawals_router, transfers_router, transactions_router
from services.account_service import create_system_account

app = FastAPI(title="P2P Payment Wallet")

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    create_system_account()

app.include_router(auth_router.router)
app.include_router(accounts_router.router)
app.include_router(deposits_router.router)
app.include_router(withdrawals_router.router)
app.include_router(transfers_router.router)
app.include_router(transactions_router.router)