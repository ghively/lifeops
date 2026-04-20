"""User Authentication Models"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """User registration model"""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    display_name: Optional[str] = Field(None, max_length=100)
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    """User login model"""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response model (without sensitive data)"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    username: str
    display_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    """Token response model"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse


class TokenRefreshRequest(BaseModel):
    """Token refresh request model"""

    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Password reset request model"""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation model"""

    token: str
    new_password: str = Field(..., min_length=8)


class PasswordChange(BaseModel):
    """Password change model (for authenticated users)"""

    old_password: str
    new_password: str = Field(..., min_length=8)
