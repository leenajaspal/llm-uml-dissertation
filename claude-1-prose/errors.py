"""Domain-level exceptions.

Services raise these framework-agnostic errors; a single exception handler in
main.py translates them into JSON HTTP responses. This keeps the business
logic free of FastAPI/HTTP details.
"""


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code = 400
    default_detail = "Bad request"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class ValidationError(AppError):
    status_code = 400
    default_detail = "Invalid request"


class AuthError(AppError):
    status_code = 401
    default_detail = "Unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    default_detail = "Forbidden"


class NotFoundError(AppError):
    status_code = 404
    default_detail = "Not found"


class ConflictError(AppError):
    status_code = 409
    default_detail = "Conflict"
