"""Model management endpoints"""

import hashlib
import io
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.core.config import settings
from app.core.database import get_db
from app.core.minio import upload_file, delete_file, get_presigned_url
from app.core.triton_repository import triton_repository
from app.models.model import Framework, Model, ModelFile, TaskType
from app.models.user import User
from app.schemas.model import (
    ModelCreate,
    ModelFileResponse,
    ModelListResponse,
    ModelResponse,
    ModelUpdate,
)

router = APIRouter()


def convert_thumbnail_to_url(model: Model) -> dict:
    """Convert model to dict with presigned thumbnail URL"""
    model_dict = {
        "id": model.id,
        "owner_id": model.owner_id,
        "name": model.name,
        "description": model.description,
        "task_type": model.task_type,
        "framework": model.framework,
        "network_type": model.network_type,
        "input_spec": model.input_spec,
        "output_spec": model.output_spec,
        "class_config": model.class_config,
        "version": model.version,
        "is_public": model.is_public,
        "thumbnail_url": None,
        "tags": model.tags,
        "metrics": model.metrics,
        "download_count": model.download_count,
        "like_count": model.like_count,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }
    
    # Generate presigned URL for thumbnail if exists
    if model.thumbnail_url:
        try:
            parts = model.thumbnail_url.split("/", 1)
            if len(parts) == 2:
                bucket, object_name = parts
                model_dict["thumbnail_url"] = get_presigned_url(bucket, object_name, expires_hours=24)
        except Exception:
            pass  # Keep thumbnail_url as None if failed
    
    return model_dict


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
    
    # Convert thumbnail paths to presigned URLs
    items = [convert_thumbnail_to_url(model) for model in models]

    return ModelListResponse(
        items=items,
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

    return convert_thumbnail_to_url(model)


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

    # Delete files from MinIO
    files_query = select(ModelFile).where(ModelFile.model_id == model_id)
    files_result = await db.execute(files_query)
    model_files = files_result.scalars().all()
    
    for model_file in model_files:
        try:
            parts = model_file.file_path.split("/", 1)
            if len(parts) == 2:
                bucket, object_name = parts
                await delete_file(bucket, object_name)
        except Exception as e:
            print(f"Warning: Failed to delete file from MinIO: {e}")
    
    # Delete thumbnail from MinIO if exists
    if model.thumbnail_url:
        try:
            parts = model.thumbnail_url.split("/", 1)
            if len(parts) == 2:
                bucket, object_name = parts
                await delete_file(bucket, object_name)
        except Exception as e:
            print(f"Warning: Failed to delete thumbnail from MinIO: {e}")
    
    # Remove model from Triton repository
    try:
        await triton_repository.remove_model(str(model_id))
    except Exception as e:
        print(f"Warning: Failed to remove model from Triton: {e}")
    
    # Delete model files from database first
    await db.execute(delete(ModelFile).where(ModelFile.model_id == model_id))
    
    # Delete the model
    await db.execute(delete(Model).where(Model.id == model_id))
    await db.commit()


# Allowed file extensions for model files
ALLOWED_EXTENSIONS = {'.pt', '.pth', '.onnx', '.engine', '.trt'}


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    import os
    return os.path.splitext(filename)[1].lower()


def calculate_checksum(data: bytes) -> str:
    """Calculate SHA256 checksum of file data"""
    return hashlib.sha256(data).hexdigest()


@router.post("/{model_id}/files", response_model=ModelFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_model_file(
    model_id: UUID,
    file: UploadFile = File(..., description="Model file (.pt, .onnx, .engine)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a model file to MinIO storage
    
    Supported formats: .pt, .pth, .onnx, .engine, .trt
    """
    # Check superuser permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能上传模型文件"
        )
    
    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # Check file extension
    file_ext = get_file_extension(file.filename or "")
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式。支持的格式: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Calculate checksum
    checksum = calculate_checksum(file_content)
    
    # Generate object path in MinIO
    object_name = f"{model_id}/{file.filename}"
    
    # Upload to MinIO
    try:
        file_data = io.BytesIO(file_content)
        minio_path = await upload_file(
            bucket=settings.MINIO_BUCKET_MODELS,
            object_name=object_name,
            file_data=file_data,
            file_size=file_size,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件上传失败: {str(e)}"
        )
    
    # Create ModelFile record
    model_file = ModelFile(
        model_id=model_id,
        file_path=minio_path,
        file_format=file_ext.lstrip('.'),
        file_size=file_size,
        checksum=checksum,
    )
    db.add(model_file)
    await db.commit()
    await db.refresh(model_file)
    
    # Auto-deploy to Triton for supported formats (onnx, engine, trt)
    triton_supported_formats = {'onnx', 'engine', 'trt'}
    if file_ext.lstrip('.').lower() in triton_supported_formats:
        try:
            deploy_result = await triton_repository.deploy_model(
                model_id=str(model_id),
                model_name=model.name,
                network_type=model.network_type.value if model.network_type else "YOLO11",
                file_format=file_ext.lstrip('.'),
                minio_bucket=settings.MINIO_BUCKET_MODELS,
                minio_object_name=object_name,
            )
            if deploy_result["success"]:
                print(f"Model {model_id} deployed to Triton: {deploy_result['triton_model_name']}")
            else:
                print(f"Warning: Failed to deploy model to Triton: {deploy_result.get('error')}")
        except Exception as e:
            # Log error but don't fail the upload
            print(f"Warning: Failed to deploy model to Triton: {e}")
    
    return model_file


@router.get("/{model_id}/files", response_model=List[ModelFileResponse])
async def list_model_files(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """List all files for a model"""
    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # Check access permission
    if not model.is_public:
        if not current_user or (model.owner_id != current_user.id and not current_user.is_superuser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此模型"
            )
    
    # Get files
    query = select(ModelFile).where(ModelFile.model_id == model_id)
    result = await db.execute(query)
    files = result.scalars().all()
    
    return files


@router.get("/{model_id}/files/{file_id}/download")
async def get_model_file_download_url(
    model_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get a presigned download URL for a model file"""
    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # Check access permission
    if not model.is_public:
        if not current_user or (model.owner_id != current_user.id and not current_user.is_superuser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此模型"
            )
    
    # Get file
    query = select(ModelFile).where(ModelFile.id == file_id, ModelFile.model_id == model_id)
    result = await db.execute(query)
    model_file = result.scalar_one_or_none()
    
    if not model_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    
    # Generate presigned URL
    try:
        # Extract object name from file path (format: "bucket/object_name")
        parts = model_file.file_path.split("/", 1)
        if len(parts) != 2:
            raise Exception("Invalid file path format")
        
        bucket, object_name = parts
        url = get_presigned_url(bucket, object_name)
        return {"download_url": url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成下载链接失败: {str(e)}"
        )


@router.delete("/{model_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_file(
    model_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a model file"""
    # Check superuser permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能删除模型文件"
        )
    
    # Get file
    query = select(ModelFile).where(ModelFile.id == file_id, ModelFile.model_id == model_id)
    result = await db.execute(query)
    model_file = result.scalar_one_or_none()
    
    if not model_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    
    # Delete from MinIO
    try:
        parts = model_file.file_path.split("/", 1)
        if len(parts) == 2:
            bucket, object_name = parts
            await delete_file(bucket, object_name)
    except Exception as e:
        # Log error but continue to delete database record
        print(f"Warning: Failed to delete file from MinIO: {e}")
    
    # Delete database record
    await db.execute(delete(ModelFile).where(ModelFile.id == file_id))
    await db.commit()


# Allowed image extensions for thumbnails
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


@router.post("/{model_id}/thumbnail", response_model=ModelResponse)
async def upload_model_thumbnail(
    model_id: UUID,
    file: UploadFile = File(..., description="Thumbnail image (.jpg, .png, .gif, .webp)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a thumbnail image for a model
    
    Supported formats: .jpg, .jpeg, .png, .gif, .webp
    """
    # Check superuser permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能上传缩略图"
        )
    
    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # Check file extension
    file_ext = get_file_extension(file.filename or "")
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的图片格式。支持的格式: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Limit file size to 5MB
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图片大小不能超过 5MB"
        )
    
    # Generate object path in MinIO
    object_name = f"{model_id}/thumbnail{file_ext}"
    
    # Delete old thumbnail if exists
    if model.thumbnail_url:
        try:
            parts = model.thumbnail_url.split("/", 1)
            if len(parts) == 2:
                old_bucket, old_object = parts
                await delete_file(old_bucket, old_object)
        except Exception:
            pass  # Ignore errors when deleting old thumbnail
    
    # Upload to MinIO
    try:
        file_data = io.BytesIO(file_content)
        content_type = file.content_type or f"image/{file_ext.lstrip('.')}"
        minio_path = await upload_file(
            bucket=settings.MINIO_BUCKET_THUMBNAILS,
            object_name=object_name,
            file_data=file_data,
            file_size=file_size,
            content_type=content_type,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"缩略图上传失败: {str(e)}"
        )
    
    # Update model thumbnail_url
    model.thumbnail_url = minio_path
    await db.commit()
    await db.refresh(model)
    
    return model


@router.get("/{model_id}/thumbnail")
async def get_model_thumbnail_url(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get a presigned URL for the model thumbnail"""
    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )
    
    # Check access permission
    if not model.is_public:
        if not current_user or (model.owner_id != current_user.id and not current_user.is_superuser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此模型"
            )
    
    if not model.thumbnail_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该模型没有缩略图"
        )
    
    # Generate presigned URL
    try:
        parts = model.thumbnail_url.split("/", 1)
        if len(parts) != 2:
            raise Exception("Invalid thumbnail path format")
        
        bucket, object_name = parts
        url = get_presigned_url(bucket, object_name, expires_hours=24)
        return {"thumbnail_url": url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成缩略图链接失败: {str(e)}"
        )

