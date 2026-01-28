"""Model management endpoints"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.core.database import get_db
from app.models.model import Framework, Model, TaskType
from app.models.user import User
from app.schemas.model import (
    ModelCreate,
    ModelListResponse,
    ModelResponse,
    ModelUpdate,
)

router = APIRouter()


@router.get("", response_model=ModelListResponse)
async def list_models(
    task_type: Optional[TaskType] = Query(None, description="Filter by task type"),
    framework: Optional[Framework] = Query(None, description="Filter by framework"),
    keyword: Optional[str] = Query(None, description="Search keyword"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """List models with filtering and pagination"""
    # Base query - show public models or user's own models
    query = select(Model)
    if current_user:
        query = query.where(
            or_(Model.is_public == True, Model.owner_id == current_user.id)
        )
    else:
        query = query.where(Model.is_public == True)

    # Apply filters
    if task_type:
        query = query.where(Model.task_type == task_type)
    if framework:
        query = query.where(Model.framework == framework)
    if keyword:
        query = query.where(
            or_(
                Model.name.ilike(f"%{keyword}%"),
                Model.description.ilike(f"%{keyword}%"),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Model.created_at.desc())

    result = await db.execute(query)
    models = result.scalars().all()

    return ModelListResponse(
        items=models,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get model details by ID"""
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    # Check access permission
    if not model.is_public:
        if not current_user or model.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to private model"
            )

    return model


@router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    model_data: ModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new model (superuser only)"""
    # 只有超级用户才能上传模型
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能上传模型"
        )
    
    model = Model(
        **model_data.model_dump(),
        owner_id=current_user.id,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@router.patch("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: UUID,
    model_data: ModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update model metadata"""
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    # 超级用户可以修改任何模型，普通用户只能修改自己的模型
    if model.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this model"
        )

    # Update fields
    update_data = model_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)

    await db.commit()
    await db.refresh(model)
    return model


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a model"""
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    if model.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this model"
        )

    # Delete the model using SQLAlchemy delete statement
    await db.execute(delete(Model).where(Model.id == model_id))
    await db.commit()
