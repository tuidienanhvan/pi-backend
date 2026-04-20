"""Custom exceptions + global handlers."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class PiException(HTTPException):
    """Base class — adds an error `code` for stable client-side handling."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code


class RateLimitExceeded(PiException):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(429, "rate_limit_exceeded", message)


class QuotaExceeded(PiException):
    def __init__(self, message: str = "Monthly quota exceeded") -> None:
        super().__init__(429, "quota_exceeded", message)


class LicenseInvalid(PiException):
    def __init__(self, message: str = "License invalid") -> None:
        super().__init__(403, "license_invalid", message)


class AIProviderError(PiException):
    def __init__(self, message: str = "AI provider error") -> None:
        super().__init__(502, "ai_provider_error", message)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global handlers to the FastAPI app."""

    @app.exception_handler(PiException)
    async def pi_exc_handler(req: Request, exc: PiException) -> JSONResponse:
        rid = getattr(req.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "code": exc.code,
                "message": exc.detail,
                "request_id": rid,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exc_handler(req: Request, exc: HTTPException) -> JSONResponse:
        rid = getattr(req.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "code": "http_error",
                "message": exc.detail,
                "request_id": rid,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(
        req: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(req.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "code": "validation_error",
                "message": "Invalid request body",
                "errors": exc.errors(),
                "request_id": rid,
            },
        )
