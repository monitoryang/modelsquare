"""Chunked upload schemas for request/response validation"""

import math
import os
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


CHUNK_SIZE_DEFAULT = 5 * 1024 * 1024  # 5MB
UPLOAD_TTL_SECONDS = 86400  # 24 hours

VIDEO_EXTENSIONS = {".mp4", ".ts", ".mov", ".avi"}
MODEL_EXTENSIONS = {".pt", ".pth", ".onnx", ".engine", ".trt"}


class UploadType(str, Enum):
    video_inference = "video_inference"
    model_file = "model_file"


class ChunkedUploadInit(BaseModel):
    """Request body for initializing a chunked upload session."""
    model_id: UUID
    filename: str = Field(..., min_length=1, max_length=256)
    file_size: int = Field(..., gt=0, le=10 * 1024 * 1024 * 1024)  # max 10GB
    chunk_size: int = Field(default=CHUNK_SIZE_DEFAULT, ge=1024 * 1024, le=50 * 1024 * 1024)
    content_type: str = Field(default="application/octet-stream")
    file_fingerprint: str = Field(..., min_length=1, max_length=512, description="Client-side file fingerprint (name+size+lastModified)")
    upload_type: UploadType = Field(default=UploadType.video_inference)
    # Inference parameters (only relevant for video_inference)
    conf_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    iou_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    sample_fps: Optional[float] = Field(default=None, ge=1.0, le=60.0)
    text_prompts: Optional[str] = Field(default=None, description="Comma-separated text prompts for OWLv2")
    owl_variant: Optional[str] = Field(default=None, description="OWL model variant")

    @field_validator("filename")
    @classmethod
    def validate_extension(cls, v: str, info) -> str:
        ext = os.path.splitext(v)[1].lower()
        upload_type = info.data.get("upload_type", UploadType.video_inference)
        if upload_type == UploadType.model_file:
            allowed = MODEL_EXTENSIONS
            label = "model"
        else:
            allowed = VIDEO_EXTENSIONS
            label = "video"
        if ext not in allowed:
            raise ValueError(
                f"Unsupported {label} format: {ext}. Allowed: {', '.join(sorted(allowed))}"
            )
        return v

    @property
    def total_chunks(self) -> int:
        return math.ceil(self.file_size / self.chunk_size)


class ChunkedUploadInitResponse(BaseModel):
    """Response after initializing a chunked upload."""
    upload_id: str
    total_chunks: int
    chunk_size: int
    expires_at: str


class ChunkUploadResponse(BaseModel):
    """Response after uploading a single chunk."""
    chunk_index: int
    uploaded_chunks: int
    total_chunks: int


class ChunkedUploadStatus(BaseModel):
    """Upload session status (for resume detection)."""
    upload_id: str
    model_id: str
    filename: str
    file_size: int
    file_fingerprint: str
    chunk_size: int
    total_chunks: int
    uploaded_chunk_indices: List[int]
    uploaded_bytes: int
    status: str  # "uploading" | "merging" | "completed" | "expired"
    created_at: str
    expires_at: str


class PendingUploadItem(BaseModel):
    """Summary of a pending upload for listing."""
    upload_id: str
    model_id: str
    filename: str
    file_size: int
    file_fingerprint: str
    uploaded_chunks: int
    total_chunks: int
    progress_percent: float
    created_at: str
    expires_at: str


class PendingUploadsResponse(BaseModel):
    """Response listing all pending uploads for a user."""
    pending_uploads: List[PendingUploadItem]
