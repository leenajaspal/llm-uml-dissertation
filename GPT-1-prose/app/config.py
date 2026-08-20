from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = "Simple Payments App"
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(Path.cwd() / "payments.sqlite3"))
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "dev-only-change-this-secret-key-before-running-in-production",
    )
    ACCESS_TOKEN_TTL_SECONDS: int = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "86400"))
    CURRENCY: str = os.getenv("CURRENCY", "GBP")
    DAILY_MOVE_LIMIT_PENCE: int = int(os.getenv("DAILY_MOVE_LIMIT_PENCE", "100000"))


settings = Settings()
