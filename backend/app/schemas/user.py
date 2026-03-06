"""User schemas for request/response validation"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=64)
    full_name: Optional[str] = Field(None, max_length=128)


class UserCreate(UserBase):
    """Schema for superuser registration (only @jouav.com emails)"""
    password: str = Field(..., min_length=8)
    verification_code: str = Field(..., min_length=6, max_length=6, description="邮箱验证码")


class UserCreateByAdmin(BaseModel):
    """Schema for superuser to create normal users (no verification code needed)"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = Field(None, max_length=128)


class SendVerificationCodeRequest(BaseModel):
    """Schema for sending verification code request"""
    email: EmailStr


class SendVerificationCodeResponse(BaseModel):
    """Schema for sending verification code response"""
    success: bool
    message: str


class UserListResponse(BaseModel):
    """Schema for paginated user list"""
    items: List['UserResponse']
    total: int
    page: int
    page_size: int


class UserStatusUpdate(BaseModel):
    """Schema for updating user status"""
    is_active: Optional[bool] = None


class UserUpdate(BaseModel):
    """Schema for user profile update"""
    full_name: Optional[str] = Field(None, max_length=128)
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    """Schema for user response"""
    id: UUID
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for authentication token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Schema for token refresh request"""
    refresh_token: str


# ============= API Key Management Schemas =============

class ApiKeyCreate(BaseModel):
    """Schema for creating a new API key"""
    name: str = Field(..., min_length=1, max_length=64, description="API Key name")
    expires_in_days: int = Field(30, ge=1, le=90, description="Days until expiration (max 90)")


class ApiKeyResponse(BaseModel):
    """Schema for API key response"""
    id: UUID
    name: str
    key: str
    is_active: bool
    expires_at: datetime
    last_used_at: Optional[datetime] = None
    created_at: datetime
    total_calls: int
    is_expired: bool
    is_valid: bool

    class Config:
        from_attributes = True


class ApiKeyListResponse(BaseModel):
    """Schema for list of API keys"""
    items: List[ApiKeyResponse]
    total: int


class ApiKeyUpdate(BaseModel):
    """Schema for updating an API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    is_active: Optional[bool] = None


# ============= API Usage Statistics Schemas =============

class ApiUsageDaily(BaseModel):
    """Schema for daily API usage"""
    date: date
    call_count: int
    success_count: int
    error_count: int
    avg_latency_ms: float

    class Config:
        from_attributes = True


class ApiUsageSummary(BaseModel):
    """Schema for API usage summary"""
    total_calls: int
    total_success: int
    total_errors: int
    avg_latency_ms: float
    daily_usage: List[ApiUsageDaily]


class ApiKeyUsageResponse(BaseModel):
    """Schema for API key with usage statistics"""
    key_info: ApiKeyResponse
    usage_summary: ApiUsageSummary
