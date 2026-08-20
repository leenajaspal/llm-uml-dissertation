from fastapi import FastAPI
from database import engine, Base
import auth_router
import accounts_router
import transactions_router

# Initialize tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payments API")

app.include_router(auth_router.router)
app.include_router(accounts_router.router)
app.include_router(transactions_router.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)