"""Model schemas for request/response validation"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.model import Framework, NetworkType, TaskType


class ClassConfig(BaseModel):
    """Class configuration with name and color"""
    name: str = Field(..., min_length=1, max_length=64, description="类别名称")
    color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$', description="颜色值，如 #FF0000")


class ModelBase(BaseModel):
    """Base model schema"""
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    task_type: TaskType
    framework: Framework
    network_type: NetworkType
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    class_config: Optional[List[ClassConfig]] = Field(default=None, description="类别配置列表")
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
    class_config: Optional[List[ClassConfig]] = Field(default=None, description="类别配置列表")
    version: Optional[str] = Field(None, max_length=16)
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class TritonStatus(BaseModel):
    """Schema for Triton model status"""
    deployed: bool = Field(default=False, description="是否已部署到Triton仓库")
    loaded: bool = Field(default=False, description="是否已在Triton中加载成功")


class ModelResponse(ModelBase):
    """Schema for model response"""
    id: UUID
    owner_id: UUID
    thumbnail_url: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    download_count: int = 0
    like_count: int = 0
    triton_status: Optional[TritonStatus] = Field(None, description="Triton服务状态")
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


class TritonDeploymentInfo(BaseModel):
    """Schema for Triton deployment information"""
    deployed: bool = Field(description="是否已部署到Triton")
    triton_model_name: Optional[str] = Field(None, description="Triton中的模型名称")
    triton_loaded: bool = Field(default=False, description="是否已在Triton中加载成功")
    error: Optional[str] = Field(None, description="部署错误信息")


class ModelFileUploadResponse(BaseModel):
    """Schema for model file upload response with Triton deployment status"""
    id: UUID
    file_path: str
    file_format: str
    file_size: Optional[int] = None
    created_at: datetime
    triton_deployment: Optional[TritonDeploymentInfo] = Field(None, description="Triton部署信息")

    class Config:
        from_attributes = True
