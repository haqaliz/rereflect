from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# Auth schemas
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    organization_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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

    class Config:
        from_attributes = True


# Organization schemas
class OrganizationResponse(BaseModel):
    id: int
    name: str
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True
