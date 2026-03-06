"""Authentication endpoints"""

import secrets
from datetime import datetime, timedelta, timezone, date
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.models.api_key import ApiKey, ApiUsage
from app.schemas.user import (
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyListResponse,
    ApiKeyUpdate,
    ApiUsageDaily,
    ApiUsageSummary,
    ApiKeyUsageResponse,
    Token,
    TokenRefresh,
    UserCreate,
    UserCreateByAdmin,
    UserLogin,
    UserResponse,
    UserListResponse,
    UserStatusUpdate,
    SendVerificationCodeRequest,
    SendVerificationCodeResponse,
)
from app.core.email_service import email_service
from app.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_token(token)
    if token_data is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Get current user if authenticated, otherwise return None"""
    if token is None:
        return None
    token_data = decode_token(token)
    if token_data is None:
        return None

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    return result.scalar_one_or_none()


@router.post("/send-verification-code", response_model=SendVerificationCodeResponse)
async def send_verification_code(request: SendVerificationCodeRequest):
    """Send verification code to email (only for @jouav.com emails)"""
    # Check if email is from jouav.com domain
    if not email_service.is_jouav_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只允许 @{settings.SUPERUSER_EMAIL_DOMAIN} 邮箱注册超级用户"
        )
    
    success, message = await email_service.send_verification_code(request.email)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    return SendVerificationCodeResponse(success=True, message=message)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new superuser (only @jouav.com emails allowed)"""
    # Check if email is from jouav.com domain
    if not email_service.is_jouav_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只允许 @{settings.SUPERUSER_EMAIL_DOMAIN} 邮箱注册超级用户"
        )
    
    # Verify email code
    code_valid, code_message = await email_service.verify_code(user_data.email, user_data.verification_code)
    if not code_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=code_message
        )
    
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册"
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用"
        )

    # Create new superuser
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        is_superuser=True,  # Always create as superuser
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login and get access token"""
    # Find user by email
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token(data={"sub": str(user.id), "email": user.email})

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token"""
    token_info = decode_token(token_data.refresh_token)
    if token_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == token_info.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token(data={"sub": str(user.id), "email": user.email})

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user


# ============= API Key Generation =============

def generate_api_key() -> str:
    """Generate a secure API key"""
    return f"msk_{secrets.token_urlsafe(32)}"


# ============= API Key Authentication Dependency =============

async def get_user_by_api_key(
    api_key: str = Query(None, alias="api_key", description="API Key for authentication"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get user by API key from query parameter (checks expiration and validity)"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing api_key parameter",
        )
    
    # Find API key in new ApiKey table
    result = await db.execute(select(ApiKey).where(ApiKey.key == api_key))
    api_key_obj = result.scalar_one_or_none()
    
    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    # Check if key is active
    if not api_key_obj.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is disabled",
        )
    
    # Check if key has expired
    if api_key_obj.is_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )
    
    # Get user
    result = await db.execute(select(User).where(User.id == api_key_obj.user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    # Update last_used_at and total_calls
    api_key_obj.last_used_at = datetime.utcnow()
    api_key_obj.total_calls += 1
    await db.commit()
    
    return user


async def record_api_usage(
    api_key: str,
    success: bool,
    latency_ms: float,
    db: AsyncSession,
) -> None:
    """Record API usage for statistics"""
    # Find API key
    result = await db.execute(select(ApiKey).where(ApiKey.key == api_key))
    api_key_obj = result.scalar_one_or_none()
    
    if not api_key_obj:
        return
    
    today = date.today()
    
    # Find or create usage record for today
    result = await db.execute(
        select(ApiUsage).where(
            and_(ApiUsage.api_key_id == api_key_obj.id, ApiUsage.date == today)
        )
    )
    usage = result.scalar_one_or_none()
    
    if not usage:
        usage = ApiUsage(
            api_key_id=api_key_obj.id,
            date=today,
            call_count=0,
            success_count=0,
            error_count=0,
            total_latency_ms=0,
        )
        db.add(usage)
    
    # Update statistics
    usage.call_count += 1
    if success:
        usage.success_count += 1
    else:
        usage.error_count += 1
    usage.total_latency_ms += int(latency_ms)
    
    await db.commit()


# ============= API Key Management Endpoints =============

@router.get("/apikeys", response_model=ApiKeyListResponse)
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for current user"""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    )
    api_keys = result.scalars().all()
    
    return ApiKeyListResponse(
        items=[
            ApiKeyResponse(
                id=key.id,
                name=key.name,
                key=key.key,
                is_active=key.is_active,
                expires_at=key.expires_at,
                last_used_at=key.last_used_at,
                created_at=key.created_at,
                total_calls=key.total_calls,
                is_expired=key.is_expired,
                is_valid=key.is_valid,
            )
            for key in api_keys
        ],
        total=len(api_keys),
    )


@router.post("/apikeys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key (max validity 90 days)"""
    # Calculate expiration date (max 90 days)
    expires_in_days = min(key_data.expires_in_days, 90)
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    
    # Generate new key
    new_key = ApiKey(
        user_id=current_user.id,
        name=key_data.name,
        key=generate_api_key(),
        expires_at=expires_at,
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    return ApiKeyResponse(
        id=new_key.id,
        name=new_key.name,
        key=new_key.key,
        is_active=new_key.is_active,
        expires_at=new_key.expires_at,
        last_used_at=new_key.last_used_at,
        created_at=new_key.created_at,
        total_calls=new_key.total_calls,
        is_expired=new_key.is_expired,
        is_valid=new_key.is_valid,
    )


@router.get("/apikeys/{key_id}", response_model=ApiKeyUsageResponse)
async def get_api_key_detail(
    key_id: UUID,
    days: int = Query(30, ge=1, le=90, description="Days of usage history to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get API key details with usage statistics"""
    result = await db.execute(
        select(ApiKey).where(
            and_(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    # Get usage statistics for the last N days
    start_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(ApiUsage).where(
            and_(ApiUsage.api_key_id == api_key.id, ApiUsage.date >= start_date)
        ).order_by(ApiUsage.date.desc())
    )
    usage_records = result.scalars().all()
    
    # Calculate summary
    total_calls = sum(u.call_count for u in usage_records)
    total_success = sum(u.success_count for u in usage_records)
    total_errors = sum(u.error_count for u in usage_records)
    total_latency = sum(u.total_latency_ms for u in usage_records)
    avg_latency = total_latency / total_calls if total_calls > 0 else 0
    
    return ApiKeyUsageResponse(
        key_info=ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=api_key.key,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
            total_calls=api_key.total_calls,
            is_expired=api_key.is_expired,
            is_valid=api_key.is_valid,
        ),
        usage_summary=ApiUsageSummary(
            total_calls=total_calls,
            total_success=total_success,
            total_errors=total_errors,
            avg_latency_ms=avg_latency,
            daily_usage=[
                ApiUsageDaily(
                    date=u.date,
                    call_count=u.call_count,
                    success_count=u.success_count,
                    error_count=u.error_count,
                    avg_latency_ms=u.avg_latency_ms,
                )
                for u in usage_records
            ],
        ),
    )


@router.patch("/apikeys/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: UUID,
    update_data: ApiKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update API key (name or active status)"""
    result = await db.execute(
        select(ApiKey).where(
            and_(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    if update_data.name is not None:
        api_key.name = update_data.name
    if update_data.is_active is not None:
        api_key.is_active = update_data.is_active
    
    await db.commit()
    await db.refresh(api_key)
    
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=api_key.key,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        total_calls=api_key.total_calls,
        is_expired=api_key.is_expired,
        is_valid=api_key.is_valid,
    )


@router.delete("/apikeys/{key_id}")
async def delete_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an API key"""
    result = await db.execute(
        select(ApiKey).where(
            and_(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    await db.delete(api_key)
    await db.commit()
    
    return {"message": "API key deleted successfully"}


# ============= User Management (Superuser Only) =============

async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure current user is a superuser"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能执行此操作"
        )
    return current_user


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """List all users (superuser only)"""
    # Get total count
    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()
    
    # Get paginated users
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    users = result.scalars().all()
    
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
    user_data: UserCreateByAdmin,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Create a normal user (superuser only, no verification code needed)"""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册"
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用"
        )

    # Create new normal user
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        is_superuser=False,  # Always create as normal user
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_status(
    user_id: UUID,
    update_data: UserStatusUpdate,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Update user status (superuser only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # Prevent superuser from deactivating themselves
    if user.id == current_user.id and update_data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用自己的账户"
        )
    
    if update_data.is_active is not None:
        user.is_active = update_data.is_active
    
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (superuser only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # Prevent superuser from deleting themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己的账户"
        )
    
    await db.delete(user)
    await db.commit()
    
    return {"message": "用户已删除"}
