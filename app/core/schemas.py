"""Shared DTOs used across routers."""

from typing import Any

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    success: bool = True
    data: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    code: str
    message: str
    request_id: str | None = None
