"""
app/identity/schemas.py — Pydantic request/response schemas for identity endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class TwoFactorRequest(BaseModel):
    temp_token: str
    totp_code: str = Field(..., min_length=6, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_2fa: bool = False
    temp_token: str | None = None  # present only when requires_2fa=True


class UserProfile(BaseModel):
    id: uuid.UUID
    username: str
    name: str
    email: str | None
    role: str
    department: str | None
    avatar_color: str
    totp_enabled: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character.")
        return v


class TOTPSetupResponse(BaseModel):
    provisioning_uri: str
    qr_code_base64: str  # PNG rendered as base64 data URI


class TOTPVerifyRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str
