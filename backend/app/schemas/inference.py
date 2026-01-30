"""Inference schemas for request/response validation"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InferenceRequest(BaseModel):
    """Base inference request schema"""
    model_id: UUID


class ImageInferenceRequest(BaseModel):
    """Schema for image inference request"""
    # Image is handled via multipart/form-data
    pass


class VideoInferenceRequest(BaseModel):
    """Schema for video inference request"""
    # Video is handled via multipart/form-data
    max_frames: Optional[int] = Field(None, ge=1, le=900)  # 30fps * 30s


class MultimodalInferenceRequest(BaseModel):
    """Schema for multimodal inference request"""
    text: Optional[str] = None
    audio_url: Optional[str] = None
    # Image is handled via multipart/form-data


class VideoTaskStatus(str, Enum):
    """Video inference task status"""
    PENDING = "pending"
    PROCESSING = "processing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoTaskCreate(BaseModel):
    """Response when video task is created"""
    task_id: str
    model_id: UUID
    status: VideoTaskStatus = VideoTaskStatus.PENDING
    message: str = "Video inference task created"


class FrameDetectionResult(BaseModel):
    """Detection result for a single frame"""
    frame_index: int
    timestamp_ms: float
    boxes: List[List[float]]
    scores: List[float]
    labels: List[int]
    class_names: List[str]


class VideoTaskProgress(BaseModel):
    """Video task progress information"""
    task_id: str
    model_id: UUID
    status: VideoTaskStatus
    total_frames: int
    processed_frames: int
    progress_percent: float
    current_stage: str  # "decoding", "inferring", "rendering"
    fps: Optional[float] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class VideoTaskResult(BaseModel):
    """Complete video inference result"""
    task_id: str
    model_id: UUID
    status: VideoTaskStatus
    total_frames: int
    processed_frames: int
    fps: float
    duration_seconds: float
    frame_results: List[FrameDetectionResult]
    class_colors: Optional[Dict[str, str]] = None
    video_info: Optional[Dict[str, Any]] = None
    render_url: Optional[str] = None
    render_video_size: Optional[int] = None  # Size of rendered video in bytes


class DetectionResult(BaseModel):
    """Schema for detection inference result"""
    boxes: List[List[float]]  # [[x1, y1, x2, y2], ...]
    scores: List[float]
    labels: List[int]
    class_names: Optional[List[str]] = None


class SegmentationResult(BaseModel):
    """Schema for segmentation inference result"""
    mask_url: Optional[str] = None
    class_ids: List[int]
    class_names: Optional[List[str]] = None


class ClassificationResult(BaseModel):
    """Schema for classification inference result"""
    class_id: int
    class_name: Optional[str] = None
    confidence: float
    top_k: Optional[List[Dict[str, Any]]] = None


class InferenceResponse(BaseModel):
    """Schema for inference response"""
    model_id: UUID
    timestamp_in: datetime
    timestamp_out: datetime
    latency_ms: float
    result_type: str  # 'detection', 'segmentation', 'classification', 'multimodal'
    result: Dict[str, Any]
    render_url: Optional[str] = None


class VideoInferenceResponse(BaseModel):
    """Schema for video inference response"""
    model_id: UUID
    total_frames: int
    processed_frames: int
    frames: List[InferenceResponse]
    video_url: Optional[str] = None


class StreamSessionCreate(BaseModel):
    """Schema for creating a stream session"""
    model_id: UUID
    stream_type: str = Field(default="rtmp", pattern="^(rtmp|webrtc|hls)$")


class StreamSessionResponse(BaseModel):
    """Schema for stream session response"""
    session_id: UUID
    model_id: UUID
    stream_url: str
    playback_url: str
    status: str
    created_at: datetime
    expires_at: datetime


class StreamStatusResponse(BaseModel):
    """Schema for stream status response"""
    session_id: UUID
    status: str  # 'active', 'inactive', 'error'
    frames_processed: int
    current_fps: float
    avg_latency_ms: float
    last_result: Optional[InferenceResponse] = None
