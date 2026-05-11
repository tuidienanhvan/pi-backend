"""Standard API response schemas for the Pi Ecosystem."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """Unified success response envelope."""

    success: bool = Field(default=True, description="Indicates if the request was successful.")
    data: T | None = Field(default=None, description="The actual payload (model, list, etc.)")
    message: str = Field(default="Operation successful", description="Human-readable status message.")
    meta: dict[str, Any] | None = Field(
        default=None, description="Additional context (pagination, timing, etc.)"
    )


class ErrorResponse(BaseModel):
    """Unified error response envelope."""

    success: bool = Field(default=False, description="Always False for errors.")
    code: str = Field(..., description="Machine-readable error code (e.g. 'not_found').")
    message: str = Field(..., description="Human-readable error message.")
    request_id: str | None = Field(default=None, description="Trace ID for debugging.")
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Detailed validation errors if applicable."
    )
