"""Public API endpoints for external model inference via API Key"""

import io
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import record_api_usage
from app.core.database import get_db
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.models.model import Model
from app.models.user import User
from app.models.api_key import ApiKey
from app.schemas.inference import PublicApiDetectionResponse

router = APIRouter()


def get_triton_model_name(model_id: str) -> str:
    """Get Triton model name based on model ID"""
    return triton_repository.get_triton_model_name(model_id)


async def get_user_and_api_key(
    api_key: str = Query(None, alias="api_key", description="API Key for authentication"),
    db: AsyncSession = Depends(get_db),
) -> Tuple[User, str]:
    """Get user and API key string from query parameter"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing api_key parameter",
        )
    
    # Find API key in ApiKey table
    result = await db.execute(select(ApiKey).where(ApiKey.key == api_key))
    api_key_obj = result.scalar_one_or_none()
    
    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    if not api_key_obj.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is disabled",
        )
    
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
    
    return user, api_key


@router.get("/models")
async def list_available_models(
    db: AsyncSession = Depends(get_db),
    user_and_key: Tuple[User, str] = Depends(get_user_and_api_key),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """
    List all available models for API inference.
    
    Only returns public models that are deployed and loaded in Triton.
    
    Query Parameters:
        - api_key: Your API key (required)
        - page: Page number (default: 1)
        - page_size: Items per page (default: 20, max: 100)
    """
    current_user, api_key = user_and_key
    
    # Query public models
    query = select(Model).where(Model.is_public == True)
    result = await db.execute(query)
    models = result.scalars().all()
    
    # Filter models that are loaded in Triton
    available_models = []
    for model in models:
        triton_model_name = get_triton_model_name(str(model.id))
        is_loaded = triton_repository.is_model_loaded(triton_model_name)
        
        if is_loaded:
            available_models.append({
                "id": str(model.id),
                "name": model.name,
                "description": model.description,
                "task_type": model.task_type.value if model.task_type else None,
                "framework": model.framework.value if model.framework else None,
                "network_type": model.network_type.value if model.network_type else None,
                "class_names": [c["name"] for c in model.class_config] if model.class_config else None,
                "input_width": model.input_width,
                "input_height": model.input_height,
            })
    
    # Pagination
    total = len(available_models)
    start = (page - 1) * page_size
    end = start + page_size
    items = available_models[start:end]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/models/{model_id}")
async def get_model_info(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_and_key: Tuple[User, str] = Depends(get_user_and_api_key),
):
    """
    Get detailed information about a specific model.
    
    Query Parameters:
        - api_key: Your API key (required)
    """
    current_user, api_key = user_and_key
    
    query = select(Model).where(Model.id == model_id, Model.is_public == True)
    result = await db.execute(query)
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found or not publicly available"
        )
    
    triton_model_name = get_triton_model_name(str(model.id))
    is_loaded = triton_repository.is_model_loaded(triton_model_name)
    
    return {
        "id": str(model.id),
        "name": model.name,
        "description": model.description,
        "task_type": model.task_type.value if model.task_type else None,
        "framework": model.framework.value if model.framework else None,
        "network_type": model.network_type.value if model.network_type else None,
        "class_names": [c["name"] for c in model.class_config] if model.class_config else None,
        "class_config": model.class_config,
        "input_width": model.input_width,
        "input_height": model.input_height,
        "is_available": is_loaded,
    }


@router.post("/models/{model_id}/detect", response_model=PublicApiDetectionResponse)
async def detect_objects(
    model_id: UUID,
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    conf_threshold: float = Form(0.25, ge=0.0, le=1.0, description="Confidence threshold"),
    iou_threshold: float = Form(0.45, ge=0.0, le=1.0, description="IoU threshold for NMS"),
    db: AsyncSession = Depends(get_db),
    user_and_key: Tuple[User, str] = Depends(get_user_and_api_key),
):
    """
    Run object detection on an image.
    
    This endpoint accepts an image file and returns detection results
    including bounding boxes, confidence scores, and class labels.
    
    Query Parameters:
        - api_key: Your API key (required)
    
    Form Parameters:
        - image: Image file (JPG/PNG, required)
        - conf_threshold: Confidence threshold (0.0-1.0, default: 0.25)
        - iou_threshold: IoU threshold for NMS (0.0-1.0, default: 0.45)
    
    Returns:
        - boxes: List of bounding boxes [[x1,y1,x2,y2], ...]
        - scores: List of confidence scores
        - labels: List of class indices
        - class_names: List of class names
        - inference_time_ms: Inference time in milliseconds
    """
    current_user, api_key = user_and_key
    timestamp_in = datetime.now(timezone.utc)
    success = False

    try:
        # Get model
        query = select(Model).where(Model.id == model_id, Model.is_public == True)
        result = await db.execute(query)
        model = result.scalar_one_or_none()

        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found or not publicly available"
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

        # Read image bytes
        image_bytes = await image.read()

        # Get Triton model name
        triton_model_name = get_triton_model_name(str(model.id))

        # Check if model is loaded
        if not triton_repository.is_model_loaded(triton_model_name):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Model is not available for inference"
            )

        # Run inference
        result = await yolo_inference_service.infer(
            model_name=triton_model_name,
            image_bytes=image_bytes,
            class_names=class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold
        )

        timestamp_out = datetime.now(timezone.utc)
        inference_time_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
        success = True

        return PublicApiDetectionResponse(
            boxes=result.get("boxes", []),
            scores=result.get("scores", []),
            labels=result.get("labels", []),
            class_names=result.get("class_names", []),
            inference_time_ms=inference_time_ms,
        )
    finally:
        # Record API usage statistics
        timestamp_out = datetime.now(timezone.utc)
        latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
        await record_api_usage(api_key, success, latency_ms, db)


@router.post("/models/{model_id}/detect/visualize")
async def detect_and_visualize(
    model_id: UUID,
    image: UploadFile = File(..., description="Image file (JPG/PNG)"),
    conf_threshold: float = Form(0.25, ge=0.0, le=1.0, description="Confidence threshold"),
    iou_threshold: float = Form(0.45, ge=0.0, le=1.0, description="IoU threshold for NMS"),
    line_width: int = Form(2, ge=1, le=10, description="Box line width"),
    font_size: int = Form(14, ge=8, le=36, description="Label font size"),
    db: AsyncSession = Depends(get_db),
    user_and_key: Tuple[User, str] = Depends(get_user_and_api_key),
):
    """
    Run object detection and return annotated image.
    
    This endpoint accepts an image file and returns the same image
    with detection boxes drawn on it.
    
    Query Parameters:
        - api_key: Your API key (required)
    
    Form Parameters:
        - image: Image file (JPG/PNG, required)
        - conf_threshold: Confidence threshold (0.0-1.0, default: 0.25)
        - iou_threshold: IoU threshold for NMS (0.0-1.0, default: 0.45)
        - line_width: Bounding box line width (1-10, default: 2)
        - font_size: Label font size (8-36, default: 14)
    
    Returns:
        - Annotated image (JPEG)
    """
    from fastapi.responses import StreamingResponse
    
    current_user, api_key = user_and_key
    timestamp_in = datetime.now(timezone.utc)
    success = False

    try:
        # Get model
        query = select(Model).where(Model.id == model_id, Model.is_public == True)
        result = await db.execute(query)
        model = result.scalar_one_or_none()

        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found or not publicly available"
            )

        # Validate image format
        if image.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format. Supported formats: JPG, PNG"
            )

        # Get class configuration
        class_names = None
        class_colors = {}
        if model.class_config:
            class_names = [c["name"] for c in model.class_config]
            class_colors = {c["name"]: c["color"] for c in model.class_config}

        # Read image bytes
        image_bytes = await image.read()

        # Get Triton model name
        triton_model_name = get_triton_model_name(str(model.id))

        # Check if model is loaded
        if not triton_repository.is_model_loaded(triton_model_name):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Model is not available for inference"
            )

        # Run inference
        detection_result = await yolo_inference_service.infer(
            model_name=triton_model_name,
            image_bytes=image_bytes,
            class_names=class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold
        )

        # Draw detections on image
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        draw = ImageDraw.Draw(img)
        
        # Try to load a font
        font = None
        font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
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

        boxes = detection_result.get("boxes", [])
        scores = detection_result.get("scores", [])
        detected_class_names = detection_result.get("class_names", [])

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box
            class_name = detected_class_names[i] if i < len(detected_class_names) else f"class_{i}"
            score = scores[i] if i < len(scores) else 0.0

            # Get color
            color_hex = class_colors.get(class_name, "#FF0000")
            color = tuple(int(color_hex.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))

            # Draw box
            draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)

            # Draw label
            label = f"{class_name}: {score*100:.1f}%"
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            padding = 4

            label_bg = [x1, y1 - text_height - padding * 2, 
                       x1 + text_width + padding * 2, y1]
            if label_bg[1] < 0:
                label_bg = [x1, y2, x1 + text_width + padding * 2, 
                           y2 + text_height + padding * 2]

            draw.rectangle(label_bg, fill=color)
            draw.text((label_bg[0] + padding, label_bg[1] + padding), 
                     label, fill=(255, 255, 255), font=font)

        # Return image
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr.seek(0)
        
        success = True

        return StreamingResponse(
            img_byte_arr,
            media_type="image/jpeg",
            headers={"Content-Disposition": "inline; filename=detection_result.jpg"}
        )
    finally:
        # Record API usage statistics
        timestamp_out = datetime.now(timezone.utc)
        latency_ms = (timestamp_out - timestamp_in).total_seconds() * 1000
        await record_api_usage(api_key, success, latency_ms, db)
