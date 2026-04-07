"""Inference endpoints for image and video processing"""

import asyncio
import io
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.core.config import settings
from app.core.database import get_db
from app.core.minio import download_file, get_file_size, stream_file
from app.core.model_adapter import create_adapter
from app.core.owl_inference import owl_inference_service
from app.core.redis import get_redis_pool
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.core.video_inference import MAX_VIDEO_SIZE, video_inference_service
from app.core.vllm_client import vllm_client
from app.models.model import Model, NetworkType
from app.models.user import User
from app.models.video_task import VideoTask, VideoTaskStatusDB
from app.schemas.inference import (
    InferenceResponse,
    UserVideoTaskListResponse,
    UserVideoTaskResponse,
    VideoExportTaskCancelResponse,
    VideoExportTaskCreate,
    VideoExportTaskProgress,
    VideoTaskCancelResponse,
    VideoTaskCreate,
    VideoTaskProgress,
    VideoTaskStatus,
    VLMBoundingBox,
    VLMChatMessage,
    VLMChatRequest,
    VLMChatResponse,
    VLMGroundingResponse,
    VLMHealthResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_triton_model_name(model_id: str) -> str:
    """Get Triton model name based on model ID"""
    return triton_repository.get_triton_model_name(model_id)


def generate_class_colors(labels: list) -> dict:
    """Generate distinct colors for each unique label.

    Args:
        labels: List of unique label strings

    Returns:
        Dictionary mapping label -> hex color string
    """
    # Predefined color palette with good contrast
    color_palette = [
        "#FF6B6B",  # Red
        "#4ECDC4",  # Teal
        "#45B7D1",  # Blue
        "#96CEB4",  # Green
        "#FFEAA7",  # Yellow
        "#DDA0DD",  # Plum
        "#98D8C8",  # Mint
        "#F7DC6F",  # Gold
        "#BB8FCE",  # Purple
        "#85C1E9",  # Light Blue
        "#F8B500",  # Orange
        "#82E0AA",  # Light Green
        "#F1948A",  # Light Red
        "#85929E",  # Gray
        "#D7BDE2",  # Light Purple
        "#A3E4D7",  # Aqua
    ]

    class_colors = {}
    for i, label in enumerate(labels):
        class_colors[label] = color_palette[i % len(color_palette)]

    return class_colors


async def _start_video_inference(
    *,
    task_id: str,
    model_id: UUID,
    model: Model,
    video_path: str,
    video_filename: str,
    video_size: int,
    conf_threshold: float,
    iou_threshold: float,
    sample_fps: Optional[float],
    text_prompts: Optional[str],
    owl_variant: Optional[str],
    db: AsyncSession,
    current_user: Optional[User],
    background_tasks: BackgroundTasks,
) -> VideoTaskCreate:
    """Shared logic: init Redis status, persist to DB, launch background inference.

    Called by both the legacy ``infer_video`` endpoint (single upload) and the
    new chunked-upload ``complete`` endpoint.
    """
    # Determine OWL vs YOLO
    _is_owl = (
        model.network_type == NetworkType.OWLv2
        or (text_prompts and text_prompts.strip())
    )

    owl_prompts: Optional[list] = None
    if text_prompts and text_prompts.strip():
        owl_prompts = [t.strip() for t in text_prompts.split(",") if t.strip()]

    if _is_owl and not owl_prompts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OWLv2 模型需要提供检测目标提示词（text_prompts），请输入检测目标后重试。"
        )
    effective_owl_variant = owl_variant or "owlv2-base-patch16"

    # Class config
    triton_model_name = get_triton_model_name(str(model_id))
    class_names = None
    class_colors = None
    if model.class_config:
        class_names = [c["name"] for c in model.class_config]
        class_colors = {c["name"]: c["color"] for c in model.class_config}
    if owl_prompts:
        class_names = owl_prompts
        class_colors = generate_class_colors(owl_prompts)

    # Init Redis
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

    # Persist to DB
    db_task = VideoTask(
        task_id=task_id,
        user_id=current_user.id if current_user else None,
        model_id=model_id,
        video_filename=video_filename,
        video_size=video_size,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
        sample_fps=sample_fps,
        background_mode=True,
        status=VideoTaskStatusDB.PENDING,
        current_stage="pending",
    )
    db.add(db_task)
    await db.commit()

    # Launch background inference via unified adapter pipeline
    adapter = create_adapter(
        network_type=model.network_type,
        triton_model_name=triton_model_name,
        class_names=class_names,
        text_prompts=owl_prompts,
        owl_variant=effective_owl_variant,
    )
    background_tasks.add_task(
        video_inference_service.process_video_unified,
        task_id=task_id,
        model_id=str(model_id),
        video_path=video_path,
        adapter=adapter,
        class_colors=class_colors,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
        sample_fps=sample_fps,
    )

    return VideoTaskCreate(
        task_id=task_id,
        model_id=model_id,
        status=VideoTaskStatus.PENDING,
        message="视频推理任务已创建，后台处理中",
        background_mode=True,
    )


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
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # WenQuanYi Chinese
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
    video: UploadFile = File(..., description="Video file (MP4, max 10GB)"),
    conf_threshold: float = Form(0.25, ge=0.0, le=1.0),
    iou_threshold: float = Form(0.45, ge=0.0, le=1.0),
    sample_fps: Optional[float] = Form(None, ge=1.0, le=60.0, description="Sample FPS for inference"),
    background_mode: bool = Form(False, description="Run inference in background mode"),
    text_prompts: Optional[str] = Form(None, description="Comma-separated text prompts for OWLv2 open-vocabulary detection"),
    owl_variant: Optional[str] = Form(None, description="OWL model variant, e.g. owlv2-base-patch16"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Submit a video inference task.

    - Video size limit: 10GB
    - Supported formats: MP4, TS
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

    # Validate video format (check MIME type and file extension)
    allowed_mimes = ["video/mp4", "video/x-msvideo", "video/quicktime", "video/mp2t", "video/vnd.dlna.mpeg-tts"]
    allowed_extensions = [".mp4", ".ts", ".mov", ".avi"]
    file_ext = os.path.splitext(video.filename or "")[1].lower()
    if video.content_type not in allowed_mimes and file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video format. Supported formats: MP4, TS"
        )

    # Check file size (read content-length header or check after reading)
    if video.size and video.size > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Video file too large. Maximum size: 10GB"
        )

    # Determine OWL vs YOLO early (before Triton checks) so we can skip
    # Triton deployment check for OWL models which use a separate inference service
    _is_owl_video = (
        model.network_type == NetworkType.OWLv2
        or (text_prompts and text_prompts.strip())
    )

    # Check if model is deployed (only required for YOLO/Triton-based models)
    if not _is_owl_video:
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
                        detail="Video file too large. Maximum size: 10GB"
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

    # Delegate to shared helper
    return await _start_video_inference(
        task_id=task_id,
        model_id=model_id,
        model=model,
        video_path=video_path,
        video_filename=video.filename or "video.mp4",
        video_size=total_size,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
        sample_fps=sample_fps,
        text_prompts=text_prompts,
        owl_variant=owl_variant,
        db=db,
        current_user=current_user,
        background_tasks=background_tasks,
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
        elapsed_seconds=task_data.get("elapsed_seconds"),
        eta_seconds=task_data.get("eta_seconds"),
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

    # Get task status from Redis; fallback to DB if Redis key has expired
    task_data = await video_inference_service.get_task_status(task_id)
    result_path = None
    render_path = None

    if task_data:
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
        result_path = task_data.get("result_path")
        render_path = task_data.get("render_path")
    else:
        # Redis expired — read paths from persistent database
        db_query = select(VideoTask).where(
            VideoTask.task_id == task_id,
            VideoTask.model_id == model_id,
        )
        db_result = await db.execute(db_query)
        db_task = db_result.scalar_one_or_none()
        if not db_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        if db_task.status.value != VideoTaskStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task is not completed. Current status: {db_task.status.value}"
            )
        result_path = db_task.result_path
        render_path = db_task.render_path

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
        if render_path:
            try:
                video_size = await get_file_size(settings.MINIO_BUCKET_TEMP, render_path)
                result_data["render_video_size"] = video_size
            except Exception:
                result_data["render_video_size"] = None

        # Supplement HLS URLs from Redis/DB for older result.json files
        # that were written before original_hls_url was included
        if "original_hls_url" not in result_data or not result_data["original_hls_url"]:
            src = task_data if task_data else None
            if not src:
                db_q = select(VideoTask).where(
                    VideoTask.task_id == task_id,
                    VideoTask.model_id == model_id,
                )
                db_r = await db.execute(db_q)
                db_t = db_r.scalar_one_or_none()
                if db_t and db_t.original_hls_url:
                    result_data["original_hls_url"] = db_t.original_hls_url
            elif src.get("original_hls_url"):
                result_data["original_hls_url"] = src["original_hls_url"]

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

    # Get task status from Redis; fallback to DB if Redis key has expired
    task_data = await video_inference_service.get_task_status(task_id)
    render_path = None

    if task_data:
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
        render_path = task_data.get("render_path")
    else:
        # Redis expired — read path from persistent database
        db_query = select(VideoTask).where(
            VideoTask.task_id == task_id,
            VideoTask.model_id == model_id,
        )
        db_result = await db.execute(db_query)
        db_task = db_result.scalar_one_or_none()
        if not db_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        if db_task.status.value != VideoTaskStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task is not completed. Current status: {db_task.status.value}"
            )
        render_path = db_task.render_path

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


@router.post("/{model_id}/infer/video/{task_id}/export", response_model=VideoExportTaskCreate)
async def create_video_export_task(
    model_id: UUID,
    task_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    selected_classes: list[str] = [],
):
    """Create export task for selected class detections"""
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

    if not selected_classes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one class must be selected"
        )

    # Ensure source task exists and completed
    source_task = await video_inference_service.get_task_status(task_id)
    if not source_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source video task not found"
        )

    if source_task.get("model_id") != str(model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found for this model"
        )

    if source_task.get("status") != VideoTaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not completed. Current status: {source_task.get('status')}"
        )

    # Build class color map for export:
    # 1) Prefer model-config colors (YOLO)
    # 2) Fallback to source task result colors (OWL/open-vocabulary)
    # 3) Auto-generate to guarantee each selected class has a distinct color
    class_colors = {}
    if model.class_config:
        class_colors = {c["name"]: c["color"] for c in model.class_config}

    result_path = source_task.get("result_path")
    if result_path:
        try:
            result_bytes = await download_file(settings.MINIO_BUCKET_TEMP, result_path)
            result_json = json.loads(result_bytes.decode("utf-8"))
            result_class_colors = result_json.get("class_colors") or {}
            if isinstance(result_class_colors, dict):
                # Fill missing classes from source task color mapping
                for cls in selected_classes:
                    if cls not in class_colors and cls in result_class_colors:
                        class_colors[cls] = result_class_colors[cls]
        except Exception:
            # Ignore result loading failures; we'll fallback to generated colors
            pass

    missing_classes = [cls for cls in selected_classes if cls not in class_colors]
    if missing_classes:
        generated_colors = generate_class_colors(selected_classes)
        for cls in missing_classes:
            class_colors[cls] = generated_colors[cls]

    export_task_id = str(uuid.uuid4())

    await video_inference_service.update_export_task_status(
        export_task_id,
        VideoTaskStatus.PENDING,
        {
            "task_id": task_id,
            "model_id": str(model_id),
            "selected_classes": selected_classes,
            "current_stage": "pending",
            "total_frames": 0,
            "processed_frames": 0,
            "progress_percent": 0,
            "elapsed_seconds": 0,
            "eta_seconds": None,
            "output_ready": False,
            "cancel_requested": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    background_tasks.add_task(
        video_inference_service.process_export_video_task,
        export_task_id=export_task_id,
        task_id=task_id,
        model_id=str(model_id),
        selected_classes=selected_classes,
        class_colors=class_colors,
    )

    return VideoExportTaskCreate(
        export_task_id=export_task_id,
        task_id=task_id,
        model_id=model_id,
        status=VideoTaskStatus.PENDING,
        message="视频导出任务已创建，正在后台处理",
    )


@router.get("/{model_id}/infer/video/{task_id}/export/{export_task_id}/status", response_model=VideoExportTaskProgress)
async def get_video_export_task_status(
    model_id: UUID,
    task_id: str,
    export_task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get video export task progress"""
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

    export_data = await video_inference_service.get_export_task_status(export_task_id)
    if not export_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export task not found"
        )

    if export_data.get("model_id") != str(model_id) or export_data.get("task_id") != task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export task not found for this model/task"
        )

    return VideoExportTaskProgress(
        export_task_id=export_task_id,
        task_id=task_id,
        model_id=model_id,
        status=VideoTaskStatus(export_data.get("status", "pending")),
        total_frames=export_data.get("total_frames", 0),
        processed_frames=export_data.get("processed_frames", 0),
        progress_percent=export_data.get("progress_percent", 0),
        current_stage=export_data.get("current_stage", "pending"),
        elapsed_seconds=export_data.get("elapsed_seconds"),
        eta_seconds=export_data.get("eta_seconds"),
        output_ready=export_data.get("output_ready", False),
        error_message=export_data.get("error_message"),
        created_at=export_data.get("created_at"),
        started_at=export_data.get("started_at"),
        completed_at=export_data.get("completed_at"),
    )


@router.post("/{model_id}/infer/video/{task_id}/export/{export_task_id}/cancel", response_model=VideoExportTaskCancelResponse)
async def cancel_video_export_task(
    model_id: UUID,
    task_id: str,
    export_task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Cancel a video export task"""
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

    export_data = await video_inference_service.get_export_task_status(export_task_id)
    if not export_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export task not found"
        )

    if export_data.get("model_id") != str(model_id) or export_data.get("task_id") != task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export task not found for this model/task"
        )

    current_status = export_data.get("status")
    if current_status in [VideoTaskStatus.COMPLETED.value, VideoTaskStatus.FAILED.value, VideoTaskStatus.CANCELLED.value]:
        return VideoExportTaskCancelResponse(
            export_task_id=export_task_id,
            status=VideoTaskStatus(current_status),
            message="任务已结束，无需取消",
        )

    await video_inference_service.request_cancel_export_task(export_task_id)

    return VideoExportTaskCancelResponse(
        export_task_id=export_task_id,
        status=VideoTaskStatus.CANCELLED,
        message="导出任务取消请求已提交",
    )


@router.get("/{model_id}/infer/video/{task_id}/export/{export_task_id}/download")
async def download_video_export_task_result(
    model_id: UUID,
    task_id: str,
    export_task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Download completed export task result"""
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

    export_data = await video_inference_service.get_export_task_status(export_task_id)
    if not export_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export task not found"
        )

    if export_data.get("model_id") != str(model_id) or export_data.get("task_id") != task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export task not found for this model/task"
        )

    if export_data.get("status") != VideoTaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export task is not completed. Current status: {export_data.get('status')}"
        )

    export_path = export_data.get("export_path")
    if not export_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export file not found"
        )

    try:
        file_size = await get_file_size(settings.MINIO_BUCKET_TEMP, export_path)
        return StreamingResponse(
            stream_file(settings.MINIO_BUCKET_TEMP, export_path),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=export_{task_id}.mp4",
                "Content-Length": str(file_size),
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download exported video: {str(e)}"
        )


@router.get("/{model_id}/infer/video/{task_id}/download/original")
async def download_original_video(
    model_id: UUID,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Download original video (without detection boxes) for frontend playback"""
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

    # Get task status from Redis; fallback to DB if Redis key has expired
    task_data = await video_inference_service.get_task_status(task_id)
    original_path = None

    if task_data:
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
        original_path = task_data.get("original_path")
    else:
        # Redis expired — read path from persistent database
        db_query = select(VideoTask).where(
            VideoTask.task_id == task_id,
            VideoTask.model_id == model_id,
        )
        db_result = await db.execute(db_query)
        db_task = db_result.scalar_one_or_none()
        if not db_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        if db_task.status.value != VideoTaskStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task is not completed. Current status: {db_task.status.value}"
            )
        original_path = db_task.original_path

    if not original_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original video not available for this task"
        )

    try:
        file_size = await get_file_size(settings.MINIO_BUCKET_TEMP, original_path)

        return StreamingResponse(
            stream_file(settings.MINIO_BUCKET_TEMP, original_path),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"inline; filename=original_{task_id}.mp4",
                "Content-Length": str(file_size),
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download original video: {str(e)}"
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


# ============= OWL Open-Vocabulary Detection APIs =============

@router.post("/{model_id}/infer/owl", response_model=InferenceResponse)
async def infer_owl(
    model_id: UUID,
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    text_prompts: str = Form(..., description="Comma-separated detection targets, e.g. 'person,car,dog'"),
    owl_variant: str = Form("owlv2-base-patch16", description="OWL model variant"),
    conf_threshold: float = Form(0.1, ge=0.0, le=1.0),
    iou_threshold: float = Form(0.3, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Run OWL open-vocabulary detection on a single image.

    Provide text prompts describing what to detect (e.g. "person,car,dog").
    Returns bounding boxes with confidence scores for each detected object.
    """
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

    # Check access permission
    if not model.is_public:
        if not current_user or model.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to private model"
            )

    # Validate network type
    if model.network_type != NetworkType.OWLv2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model network type is {model.network_type}, expected OWLv2"
        )

    # Validate image format
    if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Supported formats: JPG, PNG"
        )

    # Parse text prompts
    prompts = [t.strip() for t in text_prompts.split(",") if t.strip()]
    if not prompts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one text prompt is required"
        )

    # Validate variant
    from app.core.triton_repository import OWL_MODEL_VARIANTS
    if owl_variant not in OWL_MODEL_VARIANTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OWL variant: {owl_variant}. Available: {list(OWL_MODEL_VARIANTS.keys())}"
        )

    # Check Triton availability
    if not owl_inference_service.triton_client.client.is_server_live():
        timestamp_out = datetime.now(timezone.utc)
        latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
        return InferenceResponse(
            model_id=model_id,
            timestamp_in=timestamp_in,
            timestamp_out=timestamp_out,
            latency_ms=latency_ms,
            result_type="owl_detection",
            result={
                "status": "triton_unavailable",
                "message": "Triton Inference Server is not available.",
            },
            render_url=None,
        )

    # Read image bytes
    image_bytes = await image.read()

    # Run inference
    try:
        detection_result = await owl_inference_service.infer(
            image_bytes=image_bytes,
            text_prompts=prompts,
            variant=owl_variant,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OWL inference failed: {str(e)}"
        )

    timestamp_out = datetime.now(timezone.utc)
    latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000

    # Generate colors for detected classes
    unique_labels = list(set(detection_result.get("class_names", [])))
    class_colors = generate_class_colors(unique_labels)

    result_data = {
        "boxes": detection_result["boxes"],
        "scores": detection_result["scores"],
        "labels": detection_result["labels"],
        "class_names": detection_result["class_names"],
        "class_colors": class_colors,
        "detection_count": len(detection_result["boxes"]),
        "image_size": detection_result.get("image_size"),
        "text_prompts": prompts,
        "owl_variant": owl_variant,
        "model_info": {
            "name": model.name,
            "version": model.version,
            "network_type": model.network_type,
        },
        "inference_device": "Triton Inference Server (GPU)",
    }

    return InferenceResponse(
        model_id=model_id,
        timestamp_in=timestamp_in,
        timestamp_out=timestamp_out,
        latency_ms=latency_ms,
        result_type="owl_detection",
        result=result_data,
        render_url=None,
    )


@router.post("/{model_id}/infer/owl/render")
async def infer_owl_render(
    model_id: UUID,
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    text_prompts: str = Form(..., description="Comma-separated detection targets"),
    owl_variant: str = Form("owlv2-base-patch16", description="OWL model variant"),
    conf_threshold: float = Form(0.1, ge=0.0, le=1.0),
    iou_threshold: float = Form(0.3, ge=0.0, le=1.0),
    line_width: int = Form(2, ge=1, le=10),
    font_size: int = Form(14, ge=8, le=32),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Run OWL detection and return rendered image with detection boxes as PNG.
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

    if model.network_type != NetworkType.OWLv2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model network type is {model.network_type}, expected OWLv2"
        )

    if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Supported formats: JPG, PNG"
        )

    prompts = [t.strip() for t in text_prompts.split(",") if t.strip()]
    if not prompts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one text prompt is required"
        )

    from app.core.triton_repository import OWL_MODEL_VARIANTS
    if owl_variant not in OWL_MODEL_VARIANTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OWL variant: {owl_variant}"
        )

    if not owl_inference_service.triton_client.client.is_server_live():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Triton Inference Server is not available."
        )

    image_bytes = await image.read()

    try:
        detection_result = await owl_inference_service.infer(
            image_bytes=image_bytes,
            text_prompts=prompts,
            variant=owl_variant,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OWL inference failed: {str(e)}"
        )

    # Generate colors for detected classes
    unique_labels = list(set(detection_result.get("class_names", [])))
    class_colors = generate_class_colors(unique_labels)

    # Draw detections on original image
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
            "Content-Disposition": f"attachment; filename=owl_detection_{model_id}.png",
            "X-Detection-Count": str(len(detection_result["boxes"])),
        }
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
    from sqlalchemy import desc, func
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
        redis_eta = None
        redis_elapsed = None
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
                redis_eta = redis_data.get("eta_seconds")
                redis_elapsed = redis_data.get("elapsed_seconds")
                if redis_data.get("render_path"):
                    task.render_path = redis_data.get("render_path")
                if redis_data.get("render_video_size"):
                    task.render_video_size = redis_data.get("render_video_size")
                if redis_data.get("result_path"):
                    task.result_path = redis_data.get("result_path")
                if redis_data.get("hls_url"):
                    task.hls_url = redis_data["hls_url"]
                if redis_data.get("original_hls_url"):
                    task.original_hls_url = redis_data["original_hls_url"]
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
            elapsed_seconds=redis_elapsed,
            eta_seconds=redis_eta,
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
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Perform grounding detection using Vision-Language Model.

    This endpoint uses Qwen3-VL to detect specified objects in an image
    and returns their bounding boxes with colors for frontend Canvas rendering.

    - **image**: Upload an image file (JPG/PNG)
    - **prompt**: Describe objects to detect (e.g., "all people", "red cars", "dogs and cats")
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

    # Generate colors for each unique label (for frontend Canvas rendering)
    unique_labels = list(set(box.label for box in result.boxes))
    class_colors = generate_class_colors(unique_labels)

    # Convert boxes to response format with colors
    boxes = [
        VLMBoundingBox(
            x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2,
            label=box.label, confidence=box.confidence,
            color=class_colors.get(box.label, "#FF0000")
        )
        for box in result.boxes
    ]

    return VLMGroundingResponse(
        boxes=boxes,
        detection_count=len(boxes),
        image_width=result.image_width,
        image_height=result.image_height,
        raw_response=result.raw_response,
        latency_ms=latency_ms,
        class_colors=class_colors,
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
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Conversational grounding detection - ask questions about objects in an image.

    This endpoint combines chat capabilities with grounding detection.
    You can have a conversation about the image and get bounding boxes
    for mentioned objects. Detection results include colors for frontend Canvas rendering.

    - **image**: Upload an image file
    - **message**: Your question or detection request (e.g., "Find all the red objects")
    - **history**: Optional JSON array of previous messages for context
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

    # Generate colors for each unique label (for frontend Canvas rendering)
    unique_labels = list(set(box.label for box in boxes))
    class_colors = generate_class_colors(unique_labels)

    # Convert to response format with colors
    boxes_response = [
        {
            "x1": box.x1, "y1": box.y1, "x2": box.x2, "y2": box.y2,
            "label": box.label, "confidence": box.confidence,
            "color": class_colors.get(box.label, "#FF0000")
        }
        for box in boxes
    ]

    return {
        "response": response_text,
        "boxes": boxes_response,
        "detection_count": len(boxes_response),
        "image_width": img_width,
        "image_height": img_height,
        "class_colors": class_colors,
        "latency_ms": latency_ms,
        "usage": result.get("usage", {}),
    }


# ============= Video Task WebSocket =============


@router.websocket("/{model_id}/infer/video/{task_id}/ws")
async def websocket_video_task(
    websocket: WebSocket,
    model_id: str,
    task_id: str,
):
    """WebSocket endpoint for real-time video inference results.

    Subscribes to two Redis Pub/Sub channels:
    - ``video_task:{task_id}:frames``  – per-frame detection results
    - ``video_task:{task_id}:hls``     – HLS segment / manifest notifications

    Messages sent to the client have a ``type`` field:
    - ``connected``          – initial handshake
    - ``frame_result``       – per-frame detection dict
    - ``hls_segment``        – new .ts segment available
    - ``hls_manifest_final`` – final VOD manifest ready
    - ``task_completed``     – task finished (client should stop reconnecting)
    - ``error``              – server-side error
    """
    await websocket.accept()

    redis = await get_redis_pool()
    if not redis:
        await websocket.send_json({"type": "error", "message": "Redis unavailable"})
        await websocket.close()
        return

    # Verify task exists
    task_data = await video_inference_service.get_task_status(task_id)
    if not task_data:
        await websocket.send_json({"type": "error", "message": "Task not found"})
        await websocket.close()
        return

    # Build HLS base URL for convenience
    protocol = "https" if settings.MINIO_SECURE else "http"
    hls_playlist_url = (
        f"{protocol}://{settings.MINIO_PUBLIC_ENDPOINT}"
        f"/{settings.MINIO_BUCKET_HLS}/{task_id}/playlist.m3u8"
    )

    frames_channel = f"video_task:{task_id}:frames"
    hls_channel = f"video_task:{task_id}:hls"
    original_hls_channel = f"video_task:{task_id}:original_hls"

    pubsub = redis.pubsub()
    await pubsub.subscribe(frames_channel, hls_channel, original_hls_channel)

    # Check if original HLS is already available (late-connecting client)
    stored_original_hls = await redis.get(
        f"video_task:{task_id}:original_hls_url"
    )

    try:
        await websocket.send_json({
            "type": "connected",
            "task_id": task_id,
            "status": task_data.get("status", "unknown"),
            "hls_url": hls_playlist_url,
            "original_hls_url": (
                stored_original_hls
                or task_data.get("original_hls_url")
            ),
        })

        while True:
            # Poll Redis Pub/Sub
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=0.1,
                )

                if message and message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    data = json.loads(message["data"])

                    if channel == frames_channel:
                        await websocket.send_json({
                            "type": "frame_result",
                            **data,
                        })
                    elif channel == original_hls_channel:
                        await websocket.send_json({
                            "type": "original_hls_ready",
                            "original_hls_url": data.get(
                                "original_hls_url"
                            ),
                        })
                    elif channel == hls_channel:
                        msg_type = data.get("type", "")
                        if msg_type == "manifest_final":
                            await websocket.send_json({
                                "type": "hls_manifest_final",
                                "segments": data.get("segments", 0),
                                "hls_url": hls_playlist_url,
                            })
                        else:
                            # Build message without letting data["type"]
                            # overwrite the outer "type" key.
                            segment_msg = {
                                k: v for k, v in data.items() if k != "type"
                            }
                            segment_msg["type"] = "hls_segment"
                            await websocket.send_json(segment_msg)

            except asyncio.TimeoutError:
                pass

            # Check for client messages / keep-alive
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.01,
                )
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            # Periodically check if task is done
            current = await video_inference_service.get_task_status(task_id)
            if current and current.get("status") in ("completed", "failed", "cancelled"):
                await websocket.send_json({
                    "type": "task_completed",
                    "status": current.get("status"),
                    "hls_url": current.get("hls_url", hls_playlist_url),
                    "original_hls_url": current.get("original_hls_url"),
                })
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(
            frames_channel, hls_channel, original_hls_channel,
        )
        await pubsub.close()
