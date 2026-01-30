"""Inference endpoints for image and video processing"""

import asyncio
import io
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
from app.core.minio import download_file, get_file_size, get_presigned_url
from app.core.config import settings
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.core.video_inference import video_inference_service, MAX_VIDEO_SIZE
from app.models.model import Model
from app.models.user import User
from app.schemas.inference import (
    InferenceResponse,
    VideoInferenceResponse,
    VideoTaskCreate,
    VideoTaskProgress,
    VideoTaskResult,
    VideoTaskStatus,
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
        message="Video inference task created. Poll /status endpoint for progress."
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
        # Download and stream the video
        video_bytes = await download_file(settings.MINIO_BUCKET_TEMP, render_path)
        return StreamingResponse(
            io.BytesIO(video_bytes),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=detection_result_{task_id}.mp4",
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
