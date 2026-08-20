"""Application-specific error types and FastAPI exception handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 400

    def __init__(self, detail: str, status_code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class BusinessRuleError(AppError):
    status_code = 422


class AuthError(AppError):
    status_code = 401


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "details": exc.errors()},
        )