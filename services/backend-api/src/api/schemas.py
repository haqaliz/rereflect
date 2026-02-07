from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, Dict


# Auth schemas
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    organization_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Google OAuth schemas
class GoogleLoginRequest(BaseModel):
    """Login with Google access token (existing user)."""
    access_token: str


class GoogleSignupRequest(BaseModel):
    """Signup with Google access token (new user + organization)."""
    access_token: str
    organization_name: str = Field(min_length=2, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# User schemas
class UserResponse(BaseModel):
    id: int
    email: str
    organization_id: int
    role: str
    created_at: datetime
    weekly_digest_enabled: bool = True
    is_system_admin: bool = False

    class Config:
        from_attributes = True


# Preferences schemas
class AlertChannels(BaseModel):
    dashboard: bool = True
    email: bool = False
    slack: bool = False


class PreferencesResponse(BaseModel):
    weekly_digest_enabled: bool
    alert_channels: Optional[Dict[str, bool]] = None

    class Config:
        from_attributes = True


class PreferencesUpdateRequest(BaseModel):
    weekly_digest_enabled: Optional[bool] = None
    alert_channels: Optional[AlertChannels] = None


# Organization schemas
class OrganizationResponse(BaseModel):
    id: int
    name: str
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True
