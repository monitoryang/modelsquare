"""Chunked upload endpoints for resumable uploads (video + model files)."""

import json
import math
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.api.v1.inference import _start_video_inference
from app.api.v1.models import _finalize_model_file_upload
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.core.video_inference import MAX_VIDEO_SIZE
from app.models.model import Model, NetworkType
from app.models.user import User
from app.schemas.upload import (
    UPLOAD_TTL_SECONDS,
    ChunkedUploadInit,
    ChunkedUploadInitResponse,
    ChunkedUploadStatus,
    ChunkUploadResponse,
    PendingUploadItem,
    PendingUploadsResponse,
    UploadType,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload_dir(upload_id: str) -> str:
    """Return the temp directory path for a chunked upload."""
    return os.path.join(tempfile.gettempdir(), f"chunked_upload_{upload_id}")


def _chunk_path(upload_id: str, chunk_index: int) -> str:
    return os.path.join(_upload_dir(upload_id), f"chunk_{chunk_index:06d}")


async def _get_upload_meta(redis, upload_id: str) -> Optional[dict]:
    raw = await redis.get(f"chunked_upload:{upload_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def _set_upload_meta(redis, upload_id: str, meta: dict, ttl: int = UPLOAD_TTL_SECONDS):
    await redis.set(f"chunked_upload:{upload_id}", json.dumps(meta), ex=ttl)


async def _get_received_chunks(redis, upload_id: str) -> set[int]:
    members = await redis.smembers(f"chunked_upload:{upload_id}:chunks")
    return {int(m) for m in members}


def _merge_chunks(upload_id: str, total_chunks: int, output_path: str, expected_size: int):
    """Merge all chunks into a single file. Raises on size mismatch."""
    merged_size = 0
    with open(output_path, "wb") as out:
        for i in range(total_chunks):
            cp = _chunk_path(upload_id, i)
            with open(cp, "rb") as chunk_file:
                data = chunk_file.read()
                merged_size += len(data)
                out.write(data)

    if merged_size != expected_size:
        os.remove(output_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Merged file size mismatch: expected {expected_size}, got {merged_size}",
        )


# ---------------------------------------------------------------------------
# 1. Initialize upload session
# ---------------------------------------------------------------------------

@router.post("/init", response_model=ChunkedUploadInitResponse)
async def init_chunked_upload(
    body: ChunkedUploadInit,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Initialize a chunked upload session."""
    # Validate model exists and accessible
    result = await db.execute(select(Model).where(Model.id == body.model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    if not model.is_public:
        if not current_user or model.owner_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    is_model_file = body.upload_type == UploadType.model_file

    # Validate file size (same 10GB cap for both types)
    if body.file_size > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size: 10GB",
        )

    # Video-specific checks: Triton deployment required for inference
    if not is_model_file:
        _is_owl = (
            model.network_type == NetworkType.OWLv2
            or (body.text_prompts and body.text_prompts.strip())
        )
        if not _is_owl:
            if not triton_repository.is_model_deployed(str(body.model_id)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Model is not deployed to Triton.",
                )
            if not yolo_inference_service.triton_client.is_server_live():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Triton Inference Server is not available.",
                )

    # Model file upload requires superuser
    if is_model_file:
        if not current_user or not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有超级用户才能上传模型文件",
            )

    upload_id = str(uuid.uuid4())
    total_chunks = math.ceil(body.file_size / body.chunk_size)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=UPLOAD_TTL_SECONDS)

    # Create temp directory
    os.makedirs(_upload_dir(upload_id), exist_ok=True)

    # Store metadata in Redis
    redis = await get_redis()
    meta = {
        "upload_id": upload_id,
        "user_id": str(current_user.id) if current_user else None,
        "model_id": str(body.model_id),
        "filename": body.filename,
        "file_size": body.file_size,
        "file_fingerprint": body.file_fingerprint,
        "chunk_size": body.chunk_size,
        "total_chunks": total_chunks,
        "content_type": body.content_type,
        "upload_type": body.upload_type.value,
        "status": "uploading",
        # Inference params (only relevant for video_inference)
        "conf_threshold": body.conf_threshold,
        "iou_threshold": body.iou_threshold,
        "sample_fps": body.sample_fps,
        "text_prompts": body.text_prompts,
        "owl_variant": body.owl_variant,
        # Timestamps
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    await _set_upload_meta(redis, upload_id, meta)

    # Track per user
    if current_user:
        user_key = f"user_uploads:{current_user.id}"
        await redis.sadd(user_key, upload_id)
        await redis.expire(user_key, UPLOAD_TTL_SECONDS)

    return ChunkedUploadInitResponse(
        upload_id=upload_id,
        total_chunks=total_chunks,
        chunk_size=body.chunk_size,
        expires_at=expires_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# 2. Upload a single chunk
# ---------------------------------------------------------------------------

@router.put("/{upload_id}/chunks/{chunk_index}", response_model=ChunkUploadResponse)
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Upload a single chunk."""
    redis = await get_redis()
    meta = await _get_upload_meta(redis, upload_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found or expired")

    # Verify ownership
    if meta.get("user_id") and current_user:
        if str(current_user.id) != meta["user_id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    total_chunks = meta["total_chunks"]
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chunk_index must be in [0, {total_chunks})",
        )

    if meta.get("status") != "uploading":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Upload session is in '{meta.get('status')}' state",
        )

    # Read chunk body
    chunk_data = await request.body()
    if not chunk_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty chunk body")

    # Validate chunk size
    chunk_size = meta["chunk_size"]
    file_size = meta["file_size"]
    is_last = chunk_index == total_chunks - 1
    expected_size = file_size - chunk_index * chunk_size if is_last else chunk_size
    if len(chunk_data) != expected_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chunk size mismatch: expected {expected_size}, got {len(chunk_data)}",
        )

    # Write chunk to disk
    path = _chunk_path(upload_id, chunk_index)
    dir_path = _upload_dir(upload_id)
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path, exist_ok=True)

    with open(path, "wb") as f:
        f.write(chunk_data)

    # Mark chunk as received in Redis Set
    chunks_key = f"chunked_upload:{upload_id}:chunks"
    await redis.sadd(chunks_key, str(chunk_index))
    await redis.expire(chunks_key, UPLOAD_TTL_SECONDS)

    uploaded_count = await redis.scard(chunks_key)

    return ChunkUploadResponse(
        chunk_index=chunk_index,
        uploaded_chunks=uploaded_count,
        total_chunks=total_chunks,
    )


# ---------------------------------------------------------------------------
# 3. Complete upload (merge + dispatch by upload_type)
# ---------------------------------------------------------------------------

@router.post("/{upload_id}/complete")
async def complete_chunked_upload(
    upload_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Merge uploaded chunks and dispatch based on upload type."""
    redis = await get_redis()
    meta = await _get_upload_meta(redis, upload_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found or expired")

    if meta.get("user_id") and current_user:
        if str(current_user.id) != meta["user_id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if meta.get("status") != "uploading":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Upload session is in '{meta.get('status')}' state",
        )

    total_chunks = meta["total_chunks"]
    received = await _get_received_chunks(redis, upload_id)
    missing = sorted(set(range(total_chunks)) - received)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Missing {len(missing)} chunks: {missing[:20]}{'...' if len(missing) > 20 else ''}",
        )

    # Update status to merging
    meta["status"] = "merging"
    await _set_upload_meta(redis, upload_id, meta)

    upload_type = meta.get("upload_type", UploadType.video_inference.value)

    # Get model
    model_id = UUID(meta["model_id"])
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    # Determine output file path based on upload type
    task_id = str(uuid.uuid4())
    if upload_type == UploadType.model_file.value:
        _, ext = os.path.splitext(meta["filename"])
        merged_path = os.path.join(tempfile.gettempdir(), f"model_upload_{task_id}{ext}")
    else:
        merged_path = os.path.join(tempfile.gettempdir(), f"video_input_{task_id}.mp4")

    # Merge chunks
    try:
        _merge_chunks(upload_id, total_chunks, merged_path, meta["file_size"])
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(merged_path):
            os.remove(merged_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to merge chunks: {str(e)}",
        )

    # Clean up chunk directory
    chunk_dir = _upload_dir(upload_id)
    if os.path.isdir(chunk_dir):
        shutil.rmtree(chunk_dir, ignore_errors=True)

    # Dispatch by upload type
    try:
        if upload_type == UploadType.model_file.value:
            task_result = await _complete_model_file_upload(
                model_id=model_id,
                model=model,
                merged_path=merged_path,
                filename=meta["filename"],
                db=db,
            )
        else:
            task_result = await _complete_video_inference_upload(
                task_id=task_id,
                model_id=model_id,
                model=model,
                merged_path=merged_path,
                meta=meta,
                db=db,
                current_user=current_user,
                background_tasks=background_tasks,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete upload: {str(e)}",
        )
    finally:
        # Clean up merged file for model uploads (video cleanup is handled by inference)
        if upload_type == UploadType.model_file.value and os.path.exists(merged_path):
            os.remove(merged_path)

    # Clean up Redis upload session
    meta["status"] = "completed"
    await _set_upload_meta(redis, upload_id, meta, ttl=3600)  # keep 1h for reference
    await redis.delete(f"chunked_upload:{upload_id}:chunks")
    if current_user:
        await redis.srem(f"user_uploads:{current_user.id}", upload_id)

    return task_result


async def _complete_video_inference_upload(
    task_id: str,
    model_id: UUID,
    model: Model,
    merged_path: str,
    meta: dict,
    db: AsyncSession,
    current_user: Optional[User],
    background_tasks: BackgroundTasks,
):
    """Handle completion for video inference uploads (original behavior)."""
    return await _start_video_inference(
        task_id=task_id,
        model_id=model_id,
        model=model,
        video_path=merged_path,
        video_filename=meta["filename"],
        video_size=meta["file_size"],
        conf_threshold=meta.get("conf_threshold") or 0.25,
        iou_threshold=meta.get("iou_threshold") or 0.45,
        sample_fps=meta.get("sample_fps"),
        text_prompts=meta.get("text_prompts"),
        owl_variant=meta.get("owl_variant"),
        db=db,
        current_user=current_user,
        background_tasks=background_tasks,
    )


async def _complete_model_file_upload(
    model_id: UUID,
    model: Model,
    merged_path: str,
    filename: str,
    db: AsyncSession,
):
    """Handle completion for model file uploads: upload to MinIO + deploy to Triton."""
    return await _finalize_model_file_upload(
        model_id=model_id,
        model=model,
        file_path=merged_path,
        filename=filename,
        db=db,
    )


# ---------------------------------------------------------------------------
# 4. Get upload status (for resume)
# ---------------------------------------------------------------------------

@router.get("/{upload_id}/status", response_model=ChunkedUploadStatus)
async def get_upload_status(
    upload_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get upload session status (which chunks have been received)."""
    redis = await get_redis()
    meta = await _get_upload_meta(redis, upload_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found or expired")

    if meta.get("user_id") and current_user:
        if str(current_user.id) != meta["user_id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    received = sorted(await _get_received_chunks(redis, upload_id))
    chunk_size = meta["chunk_size"]
    uploaded_bytes = sum(
        (meta["file_size"] - i * chunk_size) if i == meta["total_chunks"] - 1 else chunk_size
        for i in received
    )

    return ChunkedUploadStatus(
        upload_id=upload_id,
        model_id=meta["model_id"],
        filename=meta["filename"],
        file_size=meta["file_size"],
        file_fingerprint=meta["file_fingerprint"],
        chunk_size=chunk_size,
        total_chunks=meta["total_chunks"],
        uploaded_chunk_indices=received,
        uploaded_bytes=uploaded_bytes,
        status=meta.get("status", "uploading"),
        created_at=meta["created_at"],
        expires_at=meta["expires_at"],
    )


# ---------------------------------------------------------------------------
# 5. Cancel / delete upload
# ---------------------------------------------------------------------------

@router.delete("/{upload_id}")
async def cancel_upload(
    upload_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Cancel an upload session and clean up resources."""
    redis = await get_redis()
    meta = await _get_upload_meta(redis, upload_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found or expired")

    if meta.get("user_id") and current_user:
        if str(current_user.id) != meta["user_id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Delete chunk directory
    chunk_dir = _upload_dir(upload_id)
    if os.path.isdir(chunk_dir):
        shutil.rmtree(chunk_dir, ignore_errors=True)

    # Delete Redis keys
    await redis.delete(f"chunked_upload:{upload_id}")
    await redis.delete(f"chunked_upload:{upload_id}:chunks")
    if current_user:
        await redis.srem(f"user_uploads:{current_user.id}", upload_id)

    return {"message": "Upload cancelled and cleaned up"}


# ---------------------------------------------------------------------------
# 6. List pending uploads for current user
# ---------------------------------------------------------------------------

@router.get("/pending", response_model=PendingUploadsResponse)
async def get_pending_uploads(
    model_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
):
    """List all pending uploads for the current user."""
    redis = await get_redis()
    user_key = f"user_uploads:{current_user.id}"
    upload_ids = await redis.smembers(user_key)

    items: list[PendingUploadItem] = []
    stale_ids: list[str] = []

    for uid in upload_ids:
        meta = await _get_upload_meta(redis, uid)
        if meta is None:
            stale_ids.append(uid)
            continue
        if meta.get("status") != "uploading":
            continue
        if model_id and meta.get("model_id") != str(model_id):
            continue

        received_count = await redis.scard(f"chunked_upload:{uid}:chunks")
        total = meta["total_chunks"]
        items.append(PendingUploadItem(
            upload_id=uid,
            model_id=meta["model_id"],
            filename=meta["filename"],
            file_size=meta["file_size"],
            file_fingerprint=meta["file_fingerprint"],
            uploaded_chunks=received_count,
            total_chunks=total,
            progress_percent=round(received_count / total * 100, 1) if total > 0 else 0,
            created_at=meta["created_at"],
            expires_at=meta["expires_at"],
        ))

    # Clean up stale references
    if stale_ids:
        await redis.srem(user_key, *stale_ids)

    return PendingUploadsResponse(pending_uploads=items)
