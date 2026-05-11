"""Request/response schemas for tenant subscription billing."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, HttpUrl


SubscribableTier = Literal["pro", "max"]


class SubscribeRequest(BaseModel):
    tier: SubscribableTier
    success_url: HttpUrl
    cancel_url: HttpUrl


class SubscribeResponse(BaseModel):
    checkout_url: str


class ChangeTierRequest(BaseModel):
    new_tier: SubscribableTier


class ChangeTierResponse(BaseModel):
    success: bool
    new_tier: SubscribableTier


class CancelSubscriptionResponse(BaseModel):
    success: bool


class SubscriptionStatusResponse(BaseModel):
    tier: str
    status: str | None = None
    period_end: datetime | None = None
    cancel_at_period_end: bool = False

