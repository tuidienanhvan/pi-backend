"""Auth DTOs — login / signup / JWT response."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    # Accept either email or username — frontend has 1 input field for both.
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class SignupRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field("", max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class UserPublic(BaseModel):
    id: int
    email: str = Field(..., max_length=255)
    name: str
    is_admin: bool
    is_verified: bool
    created_at: datetime


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int                 # seconds
    user: UserPublic


class MeResponse(UserPublic):
    # Optional summary of resources this user owns
    license_count: int = 0
    token_balance: int = 0
    tier: str = "free"
    
    # Customer profile fields
    site_url: str | None = None
    application_password: str | None = None
