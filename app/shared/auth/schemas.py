"""Auth DTOs — login / signup / JWT response."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field("", max_length=200)


class UserPublic(BaseModel):
    id: int
    email: EmailStr
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
