# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from database import engine
from routers import auth, accounts, transactions

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payments API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(accounts.router, tags=["Accounts"])
app.include_router(transactions.router, tags=["Transactions"])