from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db
from routers import accounts, auth, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="P2P Payments Wallet",
    version="1.0.0",
    description=(
        "A peer-to-peer payments wallet backed by a double-entry ledger. "
        "All monetary values are integer pence (GBP)."
    ),
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)


@app.get("/", tags=["meta"])
def root():
    return {"service": "p2p-payments-wallet", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)