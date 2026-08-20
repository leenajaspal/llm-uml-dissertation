from routers.auth_router import router as auth_router
from routers.accounts_router import router as accounts_router
from routers.deposits_router import router as deposits_router
from routers.withdrawals_router import router as withdrawals_router
from routers.transfers_router import router as transfers_router
from routers.transactions_router import router as transactions_router

__all__ = [
    "auth_router",
    "accounts_router",
    "deposits_router",
    "withdrawals_router",
    "transfers_router",
    "transactions_router"
]