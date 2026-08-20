from fastapi import FastAPI
from database import engine, Base, SessionLocal
import models
from routers import auth, accounts, transactions

Base.metadata.create_all(bind=engine)

app = FastAPI(title="P2P Payments Wallet")

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    sys_acc = db.query(models.Account).filter(models.Account.user_id == None).first()
    if not sys_acc:
        sys_acc = models.Account(account_id="SYSTEM_ACCOUNT", currency="GBP")
        db.add(sys_acc)
        db.commit()
    db.close()
