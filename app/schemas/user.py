"""
app/schemas/user.py
───────────────────
Pydantic schemas for the User model and JWT Authentication.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


# ── Token Schemas ──────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


# ── User Schemas ───────────────────────────────────────────────────────────────
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    role: str = Field("Dispatcher", description="Role: Admin or Dispatcher")
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
