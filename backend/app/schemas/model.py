"""Model schemas for request/response validation"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.model import Framework, NetworkType, TaskType


class ModelBase(BaseModel):
    """Base model schema"""
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    task_type: TaskType
    framework: Framework
    network_type: NetworkType
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    version: str = Field(default="1.0.0", max_length=16)
    is_public: bool = False
    tags: List[str] = []


class ModelCreate(ModelBase):
    """Schema for model creation"""
    pass


class ModelUpdate(BaseModel):
    """Schema for model update"""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    network_type: Optional[NetworkType] = None
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    version: Optional[str] = Field(None, max_length=16)
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class ModelResponse(ModelBase):
    """Schema for model response"""
    id: UUID
    owner_id: UUID
    thumbnail_url: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    download_count: int = 0
    like_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModelListResponse(BaseModel):
    """Schema for paginated model list response"""
    items: List[ModelResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ModelFileResponse(BaseModel):
    """Schema for model file response"""
    id: UUID
    file_path: str
    file_format: str
    file_size: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
