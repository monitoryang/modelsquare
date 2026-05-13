"""Model management endpoints"""

import asyncio
import hashlib
import io
import json
import os
import tempfile
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.core.config import settings
from app.core.database import get_db
from app.core.minio import upload_file, delete_file, get_presigned_url, get_public_url
from app.core.triton_repository import triton_repository, check_onnx_dynamic_batch
from app.core.tensorrt_converter import tensorrt_converter
from app.models.model import Framework, Model, ModelFile, NetworkType, TaskType
from app.models.video_task import VideoTask
from app.models.user import User
from app.schemas.model import (
    ModelCreate,
    ModelFileResponse,
    ModelFileUploadResponse,
    ModelListResponse,
    ModelResponse,
    ModelUpdate,
    TritonDeploymentInfo,
    TritonStatus,
    ModelDeploymentGpusResponse,
)

router = APIRouter()


def convert_thumbnail_to_url(model: Model) -> dict:
    """Convert model to dict with presigned thumbnail URL and Triton status"""
    # Get Triton status for this model
    model_id_str = str(model.id)
    network_type_str = model.network_type.value if model.network_type else ""
    is_deployed = triton_repository.is_model_deployed(model_id_str, network_type_str)
    is_loaded = triton_repository.is_model_ready(model_id_str, network_type_str) if is_deployed else False
    
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
        "triton_status": TritonStatus(deployed=is_deployed, loaded=is_loaded),
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }
    
    # Generate public URL for thumbnail if exists
    if model.thumbnail_url:
        try:
            parts = model.thumbnail_url.split("/", 1)
            if len(parts) == 2:
                bucket, object_name = parts
                model_dict["thumbnail_url"] = get_public_url(bucket, object_name)
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


@router.get("/{model_id}/deployment-gpus", response_model=ModelDeploymentGpusResponse)
async def get_model_deployment_gpus(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get current Triton deployment GPU mapping for a model"""
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    if not model.is_public:
        if not current_user or model.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to private model"
            )

    model_id_str = str(model.id)
    network_type_str = model.network_type.value if model.network_type else ""
    is_deployed = triton_repository.is_model_deployed(model_id_str, network_type_str)
    is_loaded = triton_repository.is_model_ready(model_id_str, network_type_str) if is_deployed else False

    if model.network_type == NetworkType.OWLv2:
        return ModelDeploymentGpusResponse(
            model_id=model.id,
            network_type=model.network_type,
            deployed=is_deployed,
            loaded=is_loaded,
            triton_model_name=None,
            gpu_id=None,
            owl_text_encoder_gpu_id=triton_repository.get_model_gpu_id_by_triton_name("owl_text_encoder"),
            owl_image_encoder_gpu_id=triton_repository.get_model_gpu_id_by_triton_name("owl_image_encoder_base_patch16"),
            owl_text_encoder_large_gpu_id=triton_repository.get_model_gpu_id_by_triton_name("owl_text_encoder_large"),
            owl_image_encoder_large_gpu_id=triton_repository.get_model_gpu_id_by_triton_name("owl_image_encoder_large_patch14"),
        )

    triton_model_name = triton_repository.get_triton_model_name(model_id_str)
    return ModelDeploymentGpusResponse(
        model_id=model.id,
        network_type=model.network_type,
        deployed=is_deployed,
        loaded=is_loaded,
        triton_model_name=triton_model_name,
        gpu_id=triton_repository.get_model_gpu_id(model_id_str),
        owl_text_encoder_gpu_id=None,
        owl_image_encoder_gpu_id=None,
        owl_text_encoder_large_gpu_id=None,
        owl_image_encoder_large_gpu_id=None,
    )


@router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    model_data: ModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new model (superuser only)"""
    # 只有超级用户才能注册模型
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能注册模型"
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

    # Delete related video task records to satisfy FK constraints
    await db.execute(delete(VideoTask).where(VideoTask.model_id == model_id))

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


def calculate_checksum_streaming(file_path: str, chunk_size: int = 8192) -> str:
    """Calculate SHA256 checksum by streaming from file, avoiding full memory load."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


async def _finalize_model_file_upload(
    model_id: UUID,
    model: Model,
    file_path: str,
    filename: str,
    db: AsyncSession,
) -> ModelFileUploadResponse:
    """
    Shared helper: upload a model file from disk to MinIO, create DB record,
    and auto-deploy to Triton. Used by both single-request upload and
    chunked upload completion.
    """
    file_ext = get_file_extension(filename)
    file_size = os.path.getsize(file_path)
    checksum = calculate_checksum_streaming(file_path)

    object_name = f"{model_id}/{filename}"

    # Stream upload to MinIO (no full-file memory load)
    try:
        with open(file_path, "rb") as f:
            minio_path = await upload_file(
                bucket=settings.MINIO_BUCKET_MODELS,
                object_name=object_name,
                file_data=f,
                file_size=file_size,
                content_type="application/octet-stream",
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
    triton_deployment = None
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
                print(f"Model {model_id} deployed to Triton: {deploy_result['triton_model_name']} on GPU {deploy_result.get('gpu_id', 0)}")
                gpu_info = deploy_result.get("gpu_info", {})
                triton_deployment = TritonDeploymentInfo(
                    deployed=True,
                    triton_model_name=deploy_result.get("triton_model_name"),
                    triton_loaded=deploy_result.get("triton_loaded", False),
                    gpu_id=deploy_result.get("gpu_id"),
                    gpu_name=gpu_info.get("name") if gpu_info else None,
                    error=None,
                )
            else:
                print(f"Warning: Failed to deploy model to Triton: {deploy_result.get('error')}")
                triton_deployment = TritonDeploymentInfo(
                    deployed=False,
                    triton_model_name=deploy_result.get("triton_model_name"),
                    triton_loaded=False,
                    gpu_id=None,
                    gpu_name=None,
                    error=deploy_result.get("error"),
                )
        except Exception as e:
            # Log error but don't fail the upload
            print(f"Warning: Failed to deploy model to Triton: {e}")
            triton_deployment = TritonDeploymentInfo(
                deployed=False,
                triton_model_name=None,
                triton_loaded=False,
                gpu_id=None,
                gpu_name=None,
                error=str(e),
            )

    return ModelFileUploadResponse(
        id=model_file.id,
        file_path=model_file.file_path,
        file_format=model_file.file_format,
        file_size=model_file.file_size,
        created_at=model_file.created_at,
        triton_deployment=triton_deployment,
    )


@router.post("/{model_id}/files", response_model=ModelFileUploadResponse, status_code=status.HTTP_201_CREATED)
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
            detail="只有超级用户才能注册模型文件"
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
    
    # Stream to temp file to avoid loading entire file into memory
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=file_ext)
    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                tmp.write(chunk)

        return await _finalize_model_file_upload(
            model_id=model_id,
            model=model,
            file_path=tmp_path,
            filename=file.filename or f"model{file_ext}",
            db=db,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/{model_id}/owl-files")
async def upload_owl_files(
    model_id: UUID,
    text_encoder: UploadFile = File(..., description="OWL text encoder ONNX (base, 512-dim)"),
    text_encoder_large: UploadFile = File(..., description="OWL text encoder ONNX (large, 768-dim)"),
    image_encoder_base: UploadFile = File(..., description="OWL image encoder base-patch16 ONNX"),
    image_encoder_large: UploadFile = File(..., description="OWL image encoder large-patch14 ONNX"),
    vocab_json: UploadFile = File(..., description="Tokenizer vocab.json"),
    merges_txt: UploadFile = File(..., description="Tokenizer merges.txt"),
    tokenizer_config: UploadFile = File(..., description="Tokenizer tokenizer_config.json"),
    special_tokens_map: UploadFile = File(..., description="Tokenizer special_tokens_map.json"),
    added_tokens: UploadFile = File(..., description="Tokenizer added_tokens.json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload 4 OWL ONNX files and auto-deploy to Triton with SSE progress streaming.

    Uploads text encoder base (ONNX -> Triton ONNX runtime, 512-dim),
    text encoder large (ONNX -> Triton ONNX runtime, 768-dim),
    image encoder base-patch16 (ONNX -> TensorRT -> Triton),
    image encoder large-patch14 (ONNX -> TensorRT -> Triton).

    Returns SSE stream with progress events:
    data: {"progress": X, "message": "...", "status": "deploying|completed|failed"}
    """
    import os
    import shutil
    import tempfile

    # Check superuser permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能上传OWL模型文件"
        )

    # Get model and validate
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模型不存在"
        )

    if model.network_type != NetworkType.OWLv2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此端点仅适用于 OWLv2 类型的模型"
        )

    # Validate file extensions
    for f, label in [
        (text_encoder, "text_encoder"),
        (text_encoder_large, "text_encoder_large"),
        (image_encoder_base, "image_encoder_base"),
        (image_encoder_large, "image_encoder_large"),
    ]:
        ext = get_file_extension(f.filename or "")
        if ext != ".onnx":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} 必须是 .onnx 格式文件"
            )

    # Write uploaded files to temp directory for later use
    temp_dir = tempfile.mkdtemp(prefix="owl_upload_")
    file_info = {}

    for name, file_obj in [
        ("text_encoder", text_encoder),
        ("text_encoder_large", text_encoder_large),
        ("image_encoder_base", image_encoder_base),
        ("image_encoder_large", image_encoder_large),
    ]:
        content = await file_obj.read()
        temp_path = os.path.join(temp_dir, f"{name}.onnx")
        with open(temp_path, "wb") as f:
            f.write(content)
        file_info[name] = {
            "path": temp_path,
            "size": len(content),
            "checksum": calculate_checksum(content),
        }
        del content  # Free memory early

    # Save tokenizer files to shared models volume so API container can use them
    tokenizer_dir = os.path.join(settings.TRITON_MODEL_REPOSITORY, "owl_tokenizer")
    os.makedirs(tokenizer_dir, exist_ok=True)
    tokenizer_files = {
        "vocab.json": vocab_json,
        "merges.txt": merges_txt,
        "tokenizer_config.json": tokenizer_config,
        "special_tokens_map.json": special_tokens_map,
        "added_tokens.json": added_tokens,
    }
    for fname, fobj in tokenizer_files.items():
        content = await fobj.read()
        with open(os.path.join(tokenizer_dir, fname), "wb") as f:
            f.write(content)

    # MinIO object paths
    minio_objects = {
        "text_encoder": f"{model_id}/owl_text_encoder.onnx",
        "text_encoder_large": f"{model_id}/owl_text_encoder_large.onnx",
        "image_encoder_base": f"{model_id}/owl_image_encoder_base.onnx",
        "image_encoder_large": f"{model_id}/owl_image_encoder_large.onnx",
    }

    async def generate_progress():
        try:
            # --- Phase 1: Upload to MinIO and create DB records ---

            # 1. Upload text encoder (base)
            yield f"data: {json.dumps({'progress': 5, 'message': '正在上传 Text Encoder (base) 到存储...', 'status': 'deploying'})}\n\n"

            with open(file_info["text_encoder"]["path"], "rb") as f:
                minio_path_text = await upload_file(
                    bucket=settings.MINIO_BUCKET_MODELS,
                    object_name=minio_objects["text_encoder"],
                    file_data=f,
                    file_size=file_info["text_encoder"]["size"],
                    content_type="application/octet-stream",
                )
            db.add(ModelFile(
                model_id=model_id,
                file_path=minio_path_text,
                file_format="onnx",
                file_size=file_info["text_encoder"]["size"],
                checksum=file_info["text_encoder"]["checksum"],
            ))
            await db.commit()

            yield f"data: {json.dumps({'progress': 8, 'message': 'Text Encoder (base) 上传完成', 'status': 'deploying'})}\n\n"

            # 2. Upload text encoder (large)
            yield f"data: {json.dumps({'progress': 9, 'message': '正在上传 Text Encoder (large) 到存储...', 'status': 'deploying'})}\n\n"

            with open(file_info["text_encoder_large"]["path"], "rb") as f:
                minio_path_text_large = await upload_file(
                    bucket=settings.MINIO_BUCKET_MODELS,
                    object_name=minio_objects["text_encoder_large"],
                    file_data=f,
                    file_size=file_info["text_encoder_large"]["size"],
                    content_type="application/octet-stream",
                )
            db.add(ModelFile(
                model_id=model_id,
                file_path=minio_path_text_large,
                file_format="onnx",
                file_size=file_info["text_encoder_large"]["size"],
                checksum=file_info["text_encoder_large"]["checksum"],
            ))
            await db.commit()

            yield f"data: {json.dumps({'progress': 12, 'message': 'Text Encoder (large) 上传完成', 'status': 'deploying'})}\n\n"

            # 3. Upload base image encoder
            yield f"data: {json.dumps({'progress': 14, 'message': '正在上传 Image Encoder (base-patch16)...', 'status': 'deploying'})}\n\n"

            with open(file_info["image_encoder_base"]["path"], "rb") as f:
                minio_path_base = await upload_file(
                    bucket=settings.MINIO_BUCKET_MODELS,
                    object_name=minio_objects["image_encoder_base"],
                    file_data=f,
                    file_size=file_info["image_encoder_base"]["size"],
                    content_type="application/octet-stream",
                )
            db.add(ModelFile(
                model_id=model_id,
                file_path=minio_path_base,
                file_format="onnx",
                file_size=file_info["image_encoder_base"]["size"],
                checksum=file_info["image_encoder_base"]["checksum"],
            ))
            await db.commit()

            yield f"data: {json.dumps({'progress': 20, 'message': 'Image Encoder (base-patch16) 上传完成', 'status': 'deploying'})}\n\n"

            # 4. Upload large image encoder
            yield f"data: {json.dumps({'progress': 22, 'message': '正在上传 Image Encoder (large-patch14)...', 'status': 'deploying'})}\n\n"

            with open(file_info["image_encoder_large"]["path"], "rb") as f:
                minio_path_large = await upload_file(
                    bucket=settings.MINIO_BUCKET_MODELS,
                    object_name=minio_objects["image_encoder_large"],
                    file_data=f,
                    file_size=file_info["image_encoder_large"]["size"],
                    content_type="application/octet-stream",
                )
            db.add(ModelFile(
                model_id=model_id,
                file_path=minio_path_large,
                file_format="onnx",
                file_size=file_info["image_encoder_large"]["size"],
                checksum=file_info["image_encoder_large"]["checksum"],
            ))
            await db.commit()

            yield f"data: {json.dumps({'progress': 30, 'message': 'Image Encoder (large-patch14) 上传完成', 'status': 'deploying'})}\n\n"

            # --- Phase 2: Deploy to Triton ---

            # 5. Deploy text encoder base (ONNX runtime)
            yield f"data: {json.dumps({'progress': 32, 'message': '正在部署 Text Encoder (base) 到 Triton (ONNX Runtime)...', 'status': 'deploying'})}\n\n"

            text_result = await triton_repository.deploy_owl_text_encoder(
                variant="owlv2-base-patch16",
                onnx_source_path=file_info["text_encoder"]["path"],
            )
            if not text_result.get("success"):
                error = text_result.get("error", "unknown")
                yield f"data: {json.dumps({'progress': 32, 'message': f'Text Encoder (base) 部署失败: {error}', 'status': 'failed', 'error': error})}\n\n"
                return

            text_base_gpu_id = text_result.get("gpu_id")
            yield f"data: {json.dumps({'progress': 38, 'message': 'Text Encoder (base) 部署完成', 'status': 'deploying'})}\n\n"

            # 6. Deploy text encoder large (ONNX runtime)
            yield f"data: {json.dumps({'progress': 40, 'message': '正在部署 Text Encoder (large) 到 Triton (ONNX Runtime)...', 'status': 'deploying'})}\n\n"

            text_large_result = await triton_repository.deploy_owl_text_encoder(
                variant="owlv2-large-patch14",
                onnx_source_path=file_info["text_encoder_large"]["path"],
            )
            if not text_large_result.get("success"):
                error = text_large_result.get("error", "unknown")
                yield f"data: {json.dumps({'progress': 40, 'message': f'Text Encoder (large) 部署失败: {error}', 'status': 'failed', 'error': error})}\n\n"
                return

            text_large_gpu_id = text_large_result.get("gpu_id")
            yield f"data: {json.dumps({'progress': 45, 'message': 'Text Encoder (large) 部署完成', 'status': 'deploying'})}\n\n"

            # 7. Convert and deploy base image encoder (TensorRT)
            yield f"data: {json.dumps({'progress': 48, 'message': '正在转换 Image Encoder (base-patch16) 为 TensorRT (可能需要几分钟)...', 'status': 'deploying'})}\n\n"

            base_result = await triton_repository.deploy_owl_image_encoder(
                variant="owlv2-base-patch16",
                onnx_source_path=file_info["image_encoder_base"]["path"],
            )
            if not base_result.get("success"):
                error = base_result.get("error", "unknown")
                yield f"data: {json.dumps({'progress': 65, 'message': f'Image Encoder (base) 部署失败: {error}', 'status': 'failed', 'error': error})}\n\n"
                return

            image_base_gpu_id = base_result.get("gpu_id")
            yield f"data: {json.dumps({'progress': 70, 'message': 'Image Encoder (base-patch16) 部署完成', 'status': 'deploying'})}\n\n"

            # 8. Convert and deploy large image encoder (TensorRT)
            yield f"data: {json.dumps({'progress': 72, 'message': '正在转换 Image Encoder (large-patch14) 为 TensorRT (可能需要几分钟)...', 'status': 'deploying'})}\n\n"

            large_result = await triton_repository.deploy_owl_image_encoder(
                variant="owlv2-large-patch14",
                onnx_source_path=file_info["image_encoder_large"]["path"],
            )
            if not large_result.get("success"):
                error = large_result.get("error", "unknown")
                yield f"data: {json.dumps({'progress': 90, 'message': f'Image Encoder (large) 部署失败: {error}', 'status': 'failed', 'error': error})}\n\n"
                return

            image_large_gpu_id = large_result.get("gpu_id")
            yield f"data: {json.dumps({'progress': 95, 'message': 'Image Encoder (large-patch14) 部署完成', 'status': 'deploying'})}\n\n"

            # All done
            yield f"data: {json.dumps({'progress': 100, 'message': '所有 OWL 模型文件上传并部署完成', 'status': 'completed', 'owl_text_encoder_gpu_id': text_base_gpu_id, 'owl_image_encoder_gpu_id': image_base_gpu_id, 'owl_text_encoder_large_gpu_id': text_large_gpu_id, 'owl_image_encoder_large_gpu_id': image_large_gpu_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'progress': 0, 'message': f'部署过程出错: {str(e)}', 'status': 'failed', 'error': str(e)})}\n\n"
        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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
    
    return convert_thumbnail_to_url(model)


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
    
    # Generate public URL for thumbnail
    try:
        parts = model.thumbnail_url.split("/", 1)
        if len(parts) != 2:
            raise Exception("Invalid thumbnail path format")
        
        bucket, object_name = parts
        url = get_public_url(bucket, object_name)
        return {"thumbnail_url": url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成缩略图链接失败: {str(e)}"
        )


@router.post("/{model_id}/convert-to-tensorrt")
async def convert_model_to_tensorrt(
    model_id: UUID,
    use_fp16: bool = Query(True, description="是否使用FP16精度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Convert an ONNX model to TensorRT engine format with progress streaming (SSE).
    
    This endpoint uses Server-Sent Events to stream conversion progress.
    The ONNX file must already be uploaded to the model.
    
    Returns SSE stream with progress updates in format:
    data: {"progress": 50, "message": "Optimizing layers...", "status": "converting"}
    
    Final event will have status "completed" or "failed".
    """
    # Check superuser permission
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级用户才能进行模型转换"
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
    
    # Get ONNX file for this model
    query = select(ModelFile).where(
        ModelFile.model_id == model_id,
        ModelFile.file_format == "onnx"
    )
    result = await db.execute(query)
    model_file = result.scalar_one_or_none()
    
    if not model_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到ONNX模型文件，请先上传ONNX格式的模型"
        )
    
    async def generate_progress():
        """Generator for SSE progress events"""
        progress_queue = asyncio.Queue()
        
        def progress_callback(progress: int, message: str):
            """Callback to push progress updates to queue"""
            asyncio.get_event_loop().call_soon_threadsafe(
                progress_queue.put_nowait,
                {"progress": progress, "message": message, "status": "converting"}
            )
        
        # Prepare paths
        triton_model_name = f"model_{model_id}"
        model_path = triton_repository.get_model_path(triton_model_name)
        version_path = triton_repository.get_model_version_path(triton_model_name, 1)
        
        onnx_path = version_path / "model.onnx"
        engine_path = version_path / "model.plan"
        
        # Check if ONNX already deployed to Triton repo
        if not onnx_path.exists():
            # Need to download from MinIO first
            yield f"data: {json.dumps({'progress': 0, 'message': '正在准备ONNX模型...', 'status': 'converting'})}\n\n"
            
            try:
                from app.core.minio import download_file
                
                parts = model_file.file_path.split("/", 1)
                if len(parts) != 2:
                    yield f"data: {json.dumps({'progress': 0, 'message': '文件路径格式错误', 'status': 'failed', 'error': 'Invalid file path'})}\n\n"
                    return
                
                bucket, object_name = parts
                model_data = await download_file(bucket, object_name)
                
                # Ensure directory exists
                version_path.mkdir(parents=True, exist_ok=True)
                
                with open(onnx_path, "wb") as f:
                    f.write(model_data)
                
                yield f"data: {json.dumps({'progress': 5, 'message': 'ONNX模型准备完成', 'status': 'converting'})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'progress': 0, 'message': f'下载ONNX模型失败: {str(e)}', 'status': 'failed', 'error': str(e)})}\n\n"
                return
        
        # Start conversion in background task
        # Check if ONNX has dynamic batch - warn if static
        if not check_onnx_dynamic_batch(str(onnx_path)):
            warn_data = json.dumps({
                "progress": 6,
                "message": (
                    "WARNING: 该ONNX模型的batch维度为静态(=1)，生成的TensorRT引擎将不支持批量推理。"
                    "建议使用 model.export(format='onnx', dynamic=True) 重新导出后再转换。"
                ),
                "status": "converting",
                "warning": "static_batch",
            }, ensure_ascii=False)
            yield f"data: {warn_data}\n\n"
        conversion_task = asyncio.create_task(
            tensorrt_converter.convert_onnx_to_tensorrt(
                onnx_path=str(onnx_path),
                output_path=str(engine_path),
                fp16=use_fp16,
                progress_callback=progress_callback,
            )
        )
        
        # Stream progress updates
        while not conversion_task.done():
            try:
                update = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                yield f"data: {json.dumps(update)}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                continue
        
        # Drain remaining queue items
        while not progress_queue.empty():
            update = progress_queue.get_nowait()
            yield f"data: {json.dumps(update)}\n\n"
        
        # Get conversion result
        result = conversion_task.result()
        
        if result["success"]:
            # Update Triton config to use TensorRT
            try:
                config_path = model_path / "config.pbtxt"
                if config_path.exists():
                    with open(config_path, "r") as f:
                        config_content = f.read()
                    
                    # Update platform to tensorrt_plan
                    config_content = config_content.replace(
                        'platform: "onnxruntime_onnx"',
                        'platform: "tensorrt_plan"'
                    )
                    
                    with open(config_path, "w") as f:
                        f.write(config_content)
                
                # Reload model in Triton
                await triton_repository.unload_model(triton_model_name)
                load_result = await triton_repository.load_model(triton_model_name)
                
                yield f"data: {json.dumps({'progress': 100, 'message': '转换完成，模型已加载到Triton', 'status': 'completed', 'triton_loaded': load_result})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'progress': 100, 'message': f'转换完成但Triton加载失败: {str(e)}', 'status': 'completed', 'triton_loaded': False, 'warning': str(e)})}\n\n"
        else:
            error_msg = result.get("error", "Unknown error")
            yield f"data: {json.dumps({'progress': 0, 'message': f'转换失败: {error_msg}', 'status': 'failed', 'error': error_msg})}\n\n"
    
    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


