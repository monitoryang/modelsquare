"""Inference endpoints for image and video processing"""

import asyncio
import io
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.core.database import get_db
from app.core.minio import download_file, get_file_size, get_presigned_url, stream_file
from app.core.config import settings
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.core.video_inference import video_inference_service, MAX_VIDEO_SIZE, MAX_VIDEO_DURATION
from app.models.model import Model
from app.models.user import User
from app.models.video_task import VideoTask, VideoTaskStatusDB
from app.schemas.inference import (
    InferenceResponse,
    VideoInferenceResponse,
    VideoTaskCreate,
    VideoTaskProgress,
    VideoTaskResult,
    VideoTaskStatus,
    UserVideoTaskResponse,
    UserVideoTaskListResponse,
    VideoTaskCancelResponse,
)

router = APIRouter()


def get_triton_model_name(model_id: str) -> str:
    """Get Triton model name based on model ID"""
    return triton_repository.get_triton_model_name(model_id)


@router.post("/{model_id}/infer/image", response_model=InferenceResponse)
async def infer_image(
    model_id: UUID,
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    conf_threshold: float = Form(0.25, ge=0.0, le=1.0),
    iou_threshold: float = Form(0.45, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Run inference on a single image"""
    timestamp_in = datetime.now(timezone.utc)

    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    # Check access permission for private models
    if not model.is_public:
        if not current_user or model.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to private model"
            )

    # Validate image format
    if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Supported formats: JPG, PNG"
        )

    # Get class names from model config
    class_names = None
    if model.class_config:
        class_names = [c["name"] for c in model.class_config]
    
    # Get class colors for frontend rendering
    class_colors = None
    if model.class_config:
        class_colors = {c["name"]: c["color"] for c in model.class_config}

    # Read image bytes
    image_bytes = await image.read()
    
    # Get Triton model name (based on uploaded model ID)
    triton_model_name = get_triton_model_name(str(model_id))
    
    # Check if model is deployed and ready in Triton
    if not triton_repository.is_model_deployed(str(model_id)):
        timestamp_out = datetime.now(timezone.utc)
        latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
        
        return InferenceResponse(
            model_id=model_id,
            timestamp_in=timestamp_in,
            timestamp_out=timestamp_out,
            latency_ms=latency_ms,
            result_type=model.task_type.value,
            result={
                "status": "model_not_deployed",
                "message": "Model is not deployed to Triton. Please upload an ONNX or TensorRT model file.",
                "model_name": model.name,
                "task_type": model.task_type.value,
            },
            render_url=None,
        )
    
    # Check if Triton is available
    if not yolo_inference_service.triton_client.is_server_live():
        # Fallback to mock response if Triton is not available
        timestamp_out = datetime.now(timezone.utc)
        latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
        
        return InferenceResponse(
            model_id=model_id,
            timestamp_in=timestamp_in,
            timestamp_out=timestamp_out,
            latency_ms=latency_ms,
            result_type=model.task_type.value,
            result={
                "status": "triton_unavailable",
                "message": "Triton Inference Server is not available. Please ensure it is running.",
                "model_name": model.name,
                "task_type": model.task_type.value,
            },
            render_url=None,
        )
    
    # Run inference
    try:
        detection_result = await yolo_inference_service.infer(
            model_name=triton_model_name,
            image_bytes=image_bytes,
            class_names=class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {str(e)}"
        )
    
    timestamp_out = datetime.now(timezone.utc)
    latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000

    # Build result with class colors for frontend rendering
    result_data = {
        "boxes": detection_result["boxes"],
        "scores": detection_result["scores"],
        "labels": detection_result["labels"],
        "class_names": detection_result["class_names"],
        "class_colors": class_colors,
        "detection_count": len(detection_result["boxes"]),
        "image_size": detection_result.get("image_size"),
        "input_size": detection_result.get("input_size"),
        "model_info": {
            "name": model.name,
            "version": model.version,
            "network_type": model.network_type,
            "triton_model_name": triton_model_name,
        },
        "inference_device": "Triton Inference Server (GPU)",
    }

    return InferenceResponse(
        model_id=model_id,
        timestamp_in=timestamp_in,
        timestamp_out=timestamp_out,
        latency_ms=latency_ms,
        result_type=model.task_type.value,
        result=result_data,
        render_url=None,
    )


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def draw_detections_on_image(
    image: Image.Image,
    boxes: list,
    scores: list,
    class_names: list,
    class_colors: dict,
    line_width: int = 2,
    font_size: int = 14,
) -> Image.Image:
    """Draw detection boxes and labels on image"""
    draw = ImageDraw.Draw(image)
    
    # Try Chinese font first, then fallback to DejaVu, then default
    font = None
    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",  # Chinese support
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()
    
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        class_name = class_names[i] if i < len(class_names) else f"class_{i}"
        score = scores[i] if i < len(scores) else 0.0
        
        color_hex = class_colors.get(class_name, "#FF0000") if class_colors else "#FF0000"
        color = hex_to_rgb(color_hex)
        
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)
        
        label = f"{class_name}: {score*100:.1f}%"
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        padding = 4
        
        label_bg = [x1, y1 - text_height - padding * 2, x1 + text_width + padding * 2, y1]
        if label_bg[1] < 0:
            label_bg = [x1, y2, x1 + text_width + padding * 2, y2 + text_height + padding * 2]
        
        draw.rectangle(label_bg, fill=color)
        draw.text((label_bg[0] + padding, label_bg[1] + padding), label, fill=(255, 255, 255), font=font)
    
    return image


@router.post("/{model_id}/infer/image/render")
async def infer_image_render(
    model_id: UUID,
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    conf_threshold: float = Form(0.25, ge=0.0, le=1.0),
    iou_threshold: float = Form(0.45, ge=0.0, le=1.0),
    line_width: int = Form(2, ge=1, le=10),
    font_size: int = Form(14, ge=8, le=32),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Run inference and return rendered image with detection boxes.
    Returns PNG image with detection boxes and labels drawn.
    """
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

    if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Supported formats: JPG, PNG"
        )

    class_names = None
    if model.class_config:
        class_names = [c["name"] for c in model.class_config]
    
    class_colors = None
    if model.class_config:
        class_colors = {c["name"]: c["color"] for c in model.class_config}

    image_bytes = await image.read()
    triton_model_name = get_triton_model_name(str(model_id))
    
    if not triton_repository.is_model_deployed(str(model_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model is not deployed to Triton. Please upload an ONNX or TensorRT model file."
        )
    
    if not yolo_inference_service.triton_client.is_server_live():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Triton Inference Server is not available. Please ensure it is running."
        )
    
    try:
        detection_result = await yolo_inference_service.infer(
            model_name=triton_model_name,
            image_bytes=image_bytes,
            class_names=class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {str(e)}"
        )
    
    pil_image = Image.open(io.BytesIO(image_bytes))
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    rendered_image = draw_detections_on_image(
        image=pil_image,
        boxes=detection_result["boxes"],
        scores=detection_result["scores"],
        class_names=detection_result["class_names"],
        class_colors=class_colors,
        line_width=line_width,
        font_size=font_size,
    )
    
    output_buffer = io.BytesIO()
    rendered_image.save(output_buffer, format="PNG")
    output_buffer.seek(0)
    
    return StreamingResponse(
        output_buffer,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename=detection_result_{model_id}.png",
            "X-Detection-Count": str(len(detection_result["boxes"])),
        }
    )


@router.post("/{model_id}/infer/video", response_model=VideoTaskCreate)
async def infer_video(
    model_id: UUID,
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Video file (MP4, max 2GB)"),
    conf_threshold: float = Form(0.25, ge=0.0, le=1.0),
    iou_threshold: float = Form(0.45, ge=0.0, le=1.0),
    sample_fps: Optional[float] = Form(None, ge=1.0, le=60.0, description="Sample FPS for inference"),
    background_mode: bool = Form(False, description="Run inference in background mode"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Submit a video inference task.
    
    - Video size limit: 2GB
    - Supported formats: MP4
    - Returns task_id for polling progress
    """
    # Get model
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

    # Validate video format
    if video.content_type not in ["video/mp4", "video/x-msvideo", "video/quicktime"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video format. Supported formats: MP4"
        )
    
    # Check file size (read content-length header or check after reading)
    if video.size and video.size > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Video file too large. Maximum size: 2GB"
        )
    
    # Check if model is deployed
    triton_model_name = get_triton_model_name(str(model_id))
    if not triton_repository.is_model_deployed(str(model_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model is not deployed to Triton. Please upload an ONNX or TensorRT model file."
        )
    
    # Check if Triton is available
    if not yolo_inference_service.triton_client.is_server_live():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Triton Inference Server is not available. Please ensure it is running."
        )
    
    # Generate task ID
    task_id = str(uuid.uuid4())
    
    # Save video to temp file using chunked write for large files
    temp_dir = tempfile.gettempdir()
    video_path = os.path.join(temp_dir, f"video_input_{task_id}.mp4")
    
    try:
        total_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        
        with open(video_path, "wb") as f:
            while True:
                chunk = await video.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_VIDEO_SIZE:
                    # Clean up partial file
                    f.close()
                    os.remove(video_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Video file too large. Maximum size: 2GB"
                    )
                f.write(chunk)
        
        if total_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty video file received"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save video file: {str(e)}"
        )
    
    # Get class config
    class_names = None
    class_colors = None
    if model.class_config:
        class_names = [c["name"] for c in model.class_config]
        class_colors = {c["name"]: c["color"] for c in model.class_config}
    
    # Initialize task status in Redis
    await video_inference_service.update_task_status(
        task_id=task_id,
        status=VideoTaskStatus.PENDING,
        progress_data={
            "model_id": str(model_id),
            "current_stage": "pending",
            "total_frames": 0,
            "processed_frames": 0,
            "progress_percent": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    
    # Persist task to database for user history
    db_task = VideoTask(
        task_id=task_id,
        user_id=current_user.id if current_user else None,
        model_id=model_id,
        video_filename=video.filename or "video.mp4",
        video_size=total_size,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
        sample_fps=sample_fps,
        background_mode=background_mode,
        status=VideoTaskStatusDB.PENDING,
        current_stage="pending",
    )
    db.add(db_task)
    await db.commit()
    
    # Start background processing
    background_tasks.add_task(
        video_inference_service.process_video,
        task_id=task_id,
        model_id=str(model_id),
        video_path=video_path,
        triton_model_name=triton_model_name,
        class_names=class_names,
        class_colors=class_colors,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
        sample_fps=sample_fps,
    )
    
    return VideoTaskCreate(
        task_id=task_id,
        model_id=model_id,
        status=VideoTaskStatus.PENDING,
        message="视频推理任务已创建，后台处理中" if background_mode else "Video inference task created. Poll /status endpoint for progress.",
        background_mode=background_mode,
    )


@router.get("/{model_id}/infer/video/{task_id}/status", response_model=VideoTaskProgress)
async def get_video_task_status(
    model_id: UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get video inference task progress"""
    # Verify model exists
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
    
    # Get task status from Redis
    task_data = await video_inference_service.get_task_status(task_id)
    
    if not task_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Verify task belongs to this model
    if task_data.get("model_id") != str(model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found for this model"
        )
    
    return VideoTaskProgress(
        task_id=task_id,
        model_id=model_id,
        status=VideoTaskStatus(task_data.get("status", "pending")),
        total_frames=task_data.get("total_frames", 0),
        processed_frames=task_data.get("processed_frames", 0),
        progress_percent=task_data.get("progress_percent", 0),
        current_stage=task_data.get("current_stage", "pending"),
        fps=task_data.get("fps"),
        duration_seconds=task_data.get("duration_seconds"),
        error_message=task_data.get("error_message"),
        created_at=task_data.get("created_at"),
        started_at=task_data.get("started_at"),
        completed_at=task_data.get("completed_at"),
    )


@router.get("/{model_id}/infer/video/{task_id}/result")
async def get_video_task_result(
    model_id: UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get video inference result (JSON with frame-by-frame detections)"""
    # Verify model exists
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
    
    # Get task status
    task_data = await video_inference_service.get_task_status(task_id)
    
    if not task_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    if task_data.get("model_id") != str(model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found for this model"
        )
    
    if task_data.get("status") != VideoTaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not completed. Current status: {task_data.get('status')}"
        )
    
    # Download result JSON from MinIO
    result_path = task_data.get("result_path")
    if not result_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Result file not found"
        )
    
    try:
        result_bytes = await download_file(settings.MINIO_BUCKET_TEMP, result_path)
        import json
        result_data = json.loads(result_bytes.decode("utf-8"))
        
        # Get rendered video file size
        render_path = task_data.get("render_path")
        if render_path:
            try:
                video_size = await get_file_size(settings.MINIO_BUCKET_TEMP, render_path)
                result_data["render_video_size"] = video_size
            except Exception:
                result_data["render_video_size"] = None
        
        return result_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load result: {str(e)}"
        )


@router.get("/{model_id}/infer/video/{task_id}/download")
async def download_video_result(
    model_id: UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Download rendered video with detection boxes"""
    # Verify model exists
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
    
    # Get task status
    task_data = await video_inference_service.get_task_status(task_id)
    
    if not task_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    if task_data.get("model_id") != str(model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found for this model"
        )
    
    if task_data.get("status") != VideoTaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not completed. Current status: {task_data.get('status')}"
        )
    
    # Get presigned URL for video download
    render_path = task_data.get("render_path")
    if not render_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rendered video not found"
        )
    
    try:
        # Get file size for Content-Length header
        file_size = await get_file_size(settings.MINIO_BUCKET_TEMP, render_path)
        
        # Stream the video file
        return StreamingResponse(
            stream_file(settings.MINIO_BUCKET_TEMP, render_path),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=detection_result_{task_id}.mp4",
                "Content-Length": str(file_size),
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download video: {str(e)}"
        )


@router.post("/{model_id}/infer/multimodal", response_model=InferenceResponse)
async def infer_multimodal(
    model_id: UUID,
    image: Optional[UploadFile] = File(None, description="Image input"),
    text: Optional[str] = Form(None, description="Text input"),
    audio_url: Optional[str] = Form(None, description="Audio URL"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run multimodal inference (image + text + audio)"""
    timestamp_in = datetime.now(timezone.utc)

    # Get model
    query = select(Model).where(Model.id == model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    if model.task_type.value != "multimodal":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model does not support multimodal inference"
        )

    # Check access permission
    if not model.is_public and model.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to private model"
        )

    # TODO: Implement actual multimodal inference
    timestamp_out = datetime.now(timezone.utc)
    latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000

    return InferenceResponse(
        model_id=model_id,
        timestamp_in=timestamp_in,
        timestamp_out=timestamp_out,
        latency_ms=latency_ms,
        result_type="multimodal",
        result={
            "status": "mock_result",
            "message": "Multimodal inference endpoint ready",
            "inputs_received": {
                "image": image.filename if image else None,
                "text": text,
                "audio_url": audio_url,
            },
        },
        render_url=None,
    )


# ============= User Video Task Management APIs =============

@router.get("/user/video-tasks", response_model=UserVideoTaskListResponse)
async def get_user_video_tasks(
    page: int = 1,
    page_size: int = 10,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's video inference tasks"""
    from sqlalchemy import func, desc
    from sqlalchemy.orm import selectinload
    
    # Build query
    query = select(VideoTask).where(VideoTask.user_id == current_user.id)
    
    # Filter by status if provided
    if status_filter:
        try:
            status_enum = VideoTaskStatusDB(status_filter)
            query = query.filter(VideoTask.status == status_enum)
        except ValueError:
            pass  # Invalid status, ignore filter
    
    # Get total count
    count_query = select(func.count()).select_from(VideoTask).where(VideoTask.user_id == current_user.id)
    if status_filter:
        try:
            status_enum = VideoTaskStatusDB(status_filter)
            count_query = count_query.where(VideoTask.status == status_enum)
        except ValueError:
            pass
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Add ordering and pagination
    query = query.options(selectinload(VideoTask.model)).order_by(desc(VideoTask.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Build response
    items = []
    for task in tasks:
        # Sync task status from Redis if task is still processing
        if task.status in [VideoTaskStatusDB.PENDING, VideoTaskStatusDB.PROCESSING, VideoTaskStatusDB.RENDERING]:
            redis_data = await video_inference_service.get_task_status(task.task_id)
            if redis_data:
                task.status = VideoTaskStatusDB(redis_data.get("status", task.status.value))
                task.current_stage = redis_data.get("current_stage", task.current_stage)
                task.total_frames = redis_data.get("total_frames", task.total_frames)
                task.processed_frames = redis_data.get("processed_frames", task.processed_frames)
                task.progress_percent = redis_data.get("progress_percent", task.progress_percent)
                task.fps = redis_data.get("fps", task.fps)
                task.duration_seconds = redis_data.get("duration_seconds", task.duration_seconds)
                task.error_message = redis_data.get("error_message", task.error_message)
                if redis_data.get("render_path"):
                    task.render_path = redis_data.get("render_path")
                if redis_data.get("completed_at"):
                    # Parse ISO format and remove timezone info for naive datetime storage
                    completed_dt = datetime.fromisoformat(redis_data.get("completed_at").replace("Z", "+00:00"))
                    task.completed_at = completed_dt.replace(tzinfo=None)
                # Update database
                await db.commit()
        
        # Get render video size if completed
        render_video_size = task.render_video_size
        if task.status == VideoTaskStatusDB.COMPLETED and task.render_path and not render_video_size:
            try:
                render_video_size = await get_file_size(settings.MINIO_BUCKET_TEMP, task.render_path)
                task.render_video_size = render_video_size
                await db.commit()
            except Exception:
                pass
        
        items.append(UserVideoTaskResponse(
            id=task.id,
            task_id=task.task_id,
            model_id=task.model_id,
            model_name=task.model.name if task.model else None,
            video_filename=task.video_filename,
            video_size=task.video_size,
            status=VideoTaskStatus(task.status.value),
            current_stage=task.current_stage,
            total_frames=task.total_frames,
            processed_frames=task.processed_frames,
            progress_percent=task.progress_percent,
            fps=task.fps,
            duration_seconds=task.duration_seconds,
            render_video_size=render_video_size,
            error_message=task.error_message,
            background_mode=task.background_mode,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))
    
    return UserVideoTaskListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/user/video-tasks/{task_id}/cancel", response_model=VideoTaskCancelResponse)
async def cancel_video_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a video inference task"""
    # Find task in database
    query = select(VideoTask).where(
        VideoTask.task_id == task_id,
        VideoTask.user_id == current_user.id
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Check if task can be cancelled
    if task.status in [VideoTaskStatusDB.COMPLETED, VideoTaskStatusDB.FAILED, VideoTaskStatusDB.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task.status.value}"
        )
    
    # Update task status in database
    task.status = VideoTaskStatusDB.CANCELLED
    task.error_message = "Task cancelled by user"
    await db.commit()
    
    # Update task status in Redis
    await video_inference_service.update_task_status(
        task_id=task_id,
        status=VideoTaskStatus.CANCELLED,
        progress_data={
            "model_id": str(task.model_id),
            "current_stage": "cancelled",
            "error_message": "Task cancelled by user",
        }
    )
    
    return VideoTaskCancelResponse(
        task_id=task_id,
        status=VideoTaskStatus.CANCELLED,
        message="Task has been cancelled"
    )


@router.delete("/user/video-tasks/{task_id}")
async def delete_video_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a video inference task from history"""
    # Find task in database
    query = select(VideoTask).where(
        VideoTask.task_id == task_id,
        VideoTask.user_id == current_user.id
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Delete task from database
    await db.delete(task)
    await db.commit()
    
    return {"message": "Task deleted successfully"}


# ============= VLM Grounding Detection APIs =============

from app.core.vllm_client import vllm_client
from app.schemas.inference import (
    VLMBoundingBox,
    VLMGroundingResponse,
    VLMChatMessage,
    VLMChatRequest,
    VLMChatResponse,
    VLMHealthResponse,
)


def draw_vlm_detections_on_image(
    image: Image.Image,
    boxes: list,
    line_width: int = 3,
) -> Image.Image:
    """Draw VLM detection boxes on image"""
    draw = ImageDraw.Draw(image)
    
    # Generate colors for different labels
    label_colors = {}
    color_palette = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
        "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    ]
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        font = ImageFont.load_default()
    
    for i, box in enumerate(boxes):
        label = box.label if hasattr(box, 'label') else box.get('label', 'object')
        
        # Assign color to label
        if label not in label_colors:
            label_colors[label] = color_palette[len(label_colors) % len(color_palette)]
        color = label_colors[label]
        
        # Get coordinates
        if hasattr(box, 'x1'):
            x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
            confidence = box.confidence
        else:
            x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']
            confidence = box.get('confidence')
        
        # Draw rectangle
        for offset in range(line_width):
            draw.rectangle(
                [x1 - offset, y1 - offset, x2 + offset, y2 + offset],
                outline=color
            )
        
        # Draw label background
        label_text = f"{label}"
        if confidence:
            label_text += f" {confidence:.2f}"
        
        bbox = draw.textbbox((x1, y1), label_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        draw.rectangle(
            [x1, y1 - text_height - 4, x1 + text_width + 4, y1],
            fill=color
        )
        draw.text((x1 + 2, y1 - text_height - 2), label_text, fill="white", font=font)
    
    return image


@router.get("/vlm/health", response_model=VLMHealthResponse)
async def vlm_health_check():
    """Check vLLM service health status"""
    is_healthy = await vllm_client.health_check()
    available_models = await vllm_client.get_models() if is_healthy else []
    
    return VLMHealthResponse(
        status="healthy" if is_healthy else "unavailable",
        model_name=settings.VLLM_MODEL_NAME if is_healthy else None,
        available_models=available_models,
    )


@router.post("/vlm/grounding", response_model=VLMGroundingResponse)
async def vlm_grounding_detection(
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    prompt: str = Form(..., description="Objects to detect, e.g., 'person, car, dog'"),
    render_boxes: bool = Form(True, description="Whether to render boxes on image"),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Perform grounding detection using Vision-Language Model.
    
    This endpoint uses Qwen3-VL to detect specified objects in an image
    and returns their bounding boxes. The detected boxes can be rendered
    on the original image.
    
    - **image**: Upload an image file (JPG/PNG)
    - **prompt**: Describe objects to detect (e.g., "all people", "red cars", "dogs and cats")
    - **render_boxes**: If True, returns a URL to the image with drawn detection boxes
    """
    timestamp_in = datetime.now(timezone.utc)
    
    # Validate image format
    if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Supported formats: JPG, PNG"
        )
    
    # Check vLLM service health
    is_healthy = await vllm_client.health_check()
    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VLM service is not available. Please ensure vLLM server is running."
        )
    
    # Read image bytes
    image_bytes = await image.read()
    
    # Perform grounding detection
    try:
        result = await vllm_client.grounding_detection(
            image_bytes=image_bytes,
            prompt=prompt,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"VLM inference failed: {str(e)}"
        )
    
    timestamp_out = datetime.now(timezone.utc)
    latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
    
    # Convert boxes to response format
    boxes = [
        VLMBoundingBox(
            x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2,
            label=box.label, confidence=box.confidence
        )
        for box in result.boxes
    ]
    
    render_url = None
    
    # Render boxes on image if requested
    if render_boxes and boxes:
        try:
            from app.core.minio import upload_file
            
            # Open and draw on image
            pil_image = Image.open(io.BytesIO(image_bytes))
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            
            rendered_image = draw_vlm_detections_on_image(pil_image, boxes)
            
            # Save to bytes
            output_buffer = io.BytesIO()
            rendered_image.save(output_buffer, format="JPEG", quality=95)
            output_buffer.seek(0)
            
            # Upload to MinIO
            render_filename = f"vlm_render_{uuid.uuid4().hex[:8]}.jpg"
            await upload_file(
                settings.MINIO_BUCKET_TEMP,
                render_filename,
                output_buffer.getvalue(),
                content_type="image/jpeg"
            )
            
            # Get presigned URL
            render_url = await get_presigned_url(
                settings.MINIO_BUCKET_TEMP,
                render_filename,
                expires=3600  # 1 hour
            )
        except Exception as e:
            # Log error but don't fail the request
            print(f"Warning: Failed to render boxes on image: {e}")
    
    return VLMGroundingResponse(
        boxes=boxes,
        detection_count=len(boxes),
        image_width=result.image_width,
        image_height=result.image_height,
        raw_response=result.raw_response,
        latency_ms=latency_ms,
        render_url=render_url,
    )


@router.post("/vlm/chat", response_model=VLMChatResponse)
async def vlm_chat_completion(
    request: VLMChatRequest,
    image: Optional[UploadFile] = File(None, description="Optional image for vision tasks"),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Chat completion with Vision-Language Model.
    
    Send a conversation history and optionally an image to get a response
    from the VLM. Supports multi-turn conversations.
    
    - **messages**: List of messages with role (system/user/assistant) and content
    - **image**: Optional image file for vision-related questions
    - **max_tokens**: Maximum tokens in response (default: 2048)
    - **temperature**: Sampling temperature (default: 0.7)
    """
    timestamp_in = datetime.now(timezone.utc)
    
    # Check vLLM service health
    is_healthy = await vllm_client.health_check()
    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VLM service is not available. Please ensure vLLM server is running."
        )
    
    # Read image bytes if provided
    image_bytes = None
    if image:
        if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format. Supported formats: JPG, PNG"
            )
        image_bytes = await image.read()
    
    # Convert messages to dict format
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    # Perform chat completion
    try:
        result = await vllm_client.chat_completion(
            messages=messages,
            image_bytes=image_bytes,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"VLM chat completion failed: {str(e)}"
        )
    
    timestamp_out = datetime.now(timezone.utc)
    latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
    
    # Extract response
    choice = result["choices"][0]
    response_message = choice["message"]
    
    return VLMChatResponse(
        message=VLMChatMessage(
            role=response_message["role"],
            content=response_message["content"],
        ),
        finish_reason=choice.get("finish_reason", "stop"),
        usage=result.get("usage", {}),
        latency_ms=latency_ms,
    )


@router.post("/vlm/grounding/chat")
async def vlm_grounding_chat(
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    message: str = Form(..., description="User message about the image"),
    history: Optional[str] = Form(None, description="JSON array of previous messages"),
    render_boxes: bool = Form(True, description="Whether to render detected boxes"),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Conversational grounding detection - ask questions about objects in an image.
    
    This endpoint combines chat capabilities with grounding detection.
    You can have a conversation about the image and get bounding boxes
    for mentioned objects.
    
    - **image**: Upload an image file
    - **message**: Your question or detection request (e.g., "Find all the red objects")
    - **history**: Optional JSON array of previous messages for context
    - **render_boxes**: If True, returns rendered image with boxes
    """
    timestamp_in = datetime.now(timezone.utc)
    
    # Validate image format
    if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Supported formats: JPG, PNG"
        )
    
    # Check vLLM service health
    is_healthy = await vllm_client.health_check()
    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VLM service is not available"
        )
    
    # Parse history if provided
    messages_history = []
    if history:
        try:
            messages_history = json.loads(history)
        except json.JSONDecodeError:
            pass
    
    # Read image bytes
    image_bytes = await image.read()
    
    # Build system prompt for grounding conversation
    system_prompt = """You are an intelligent visual assistant that can detect and locate objects in images.
When the user asks about objects in the image, you should:
1. Describe what you see
2. If they ask to detect/find/locate specific objects, output bounding boxes in JSON format

For detection requests, output a JSON array like:
[{"bbox_2d": [x1, y1, x2, y2], "label": "object_name"}, ...]
Coordinates should be in 0-1000 normalized format.

Be conversational and helpful. You can answer general questions about the image as well."""

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(messages_history)
    messages.append({"role": "user", "content": message})
    
    # Perform chat completion with image
    try:
        result = await vllm_client.chat_completion(
            messages=messages,
            image_bytes=image_bytes,
            max_tokens=2048,
            temperature=0.3,  # Lower temperature for more precise detection
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"VLM inference failed: {str(e)}"
        )
    
    timestamp_out = datetime.now(timezone.utc)
    latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
    
    # Extract response
    response_text = result["choices"][0]["message"]["content"]
    
    # Try to parse bounding boxes from response
    img_width, img_height = vllm_client._get_image_size(image_bytes)
    boxes = vllm_client._parse_grounding_response(response_text, img_width, img_height)
    
    # Convert to response format
    boxes_response = [
        {
            "x1": box.x1, "y1": box.y1, "x2": box.x2, "y2": box.y2,
            "label": box.label, "confidence": box.confidence
        }
        for box in boxes
    ]
    
    render_url = None
    
    # Render boxes on image if requested and boxes were detected
    if render_boxes and boxes:
        try:
            from app.core.minio import upload_file
            
            pil_image = Image.open(io.BytesIO(image_bytes))
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            
            rendered_image = draw_vlm_detections_on_image(pil_image, boxes)
            
            output_buffer = io.BytesIO()
            rendered_image.save(output_buffer, format="JPEG", quality=95)
            output_buffer.seek(0)
            
            render_filename = f"vlm_chat_{uuid.uuid4().hex[:8]}.jpg"
            await upload_file(
                settings.MINIO_BUCKET_TEMP,
                render_filename,
                output_buffer.getvalue(),
                content_type="image/jpeg"
            )
            
            render_url = await get_presigned_url(
                settings.MINIO_BUCKET_TEMP,
                render_filename,
                expires=3600
            )
        except Exception as e:
            print(f"Warning: Failed to render boxes: {e}")
    
    return {
        "response": response_text,
        "boxes": boxes_response,
        "detection_count": len(boxes_response),
        "image_width": img_width,
        "image_height": img_height,
        "render_url": render_url,
        "latency_ms": latency_ms,
        "usage": result.get("usage", {}),
    }
