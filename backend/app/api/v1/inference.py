"""Inference endpoints for image and video processing"""

import io
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.core.database import get_db
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.models.model import Model
from app.models.user import User
from app.schemas.inference import InferenceResponse, VideoInferenceResponse

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
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
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


@router.post("/{model_id}/infer/video", response_model=VideoInferenceResponse)
async def infer_video(
    model_id: UUID,
    video: UploadFile = File(..., description="Video file (MP4/H.264, max 30s)"),
    max_frames: Optional[int] = Form(None, ge=1, le=900),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Run inference on a video file (max 30 seconds)"""
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

    # Validate video format
    if video.content_type not in ["video/mp4", "video/x-msvideo"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video format. Supported formats: MP4"
        )

    # TODO: Implement actual video inference with FFmpeg frame extraction + Triton
    timestamp_out = datetime.now(timezone.utc)

    return VideoInferenceResponse(
        model_id=model_id,
        total_frames=0,
        processed_frames=0,
        frames=[],
        video_url=None,
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
