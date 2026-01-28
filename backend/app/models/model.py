"""Model entity for AI models"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class TaskType(str, Enum):
    """Model task types"""
    CLASSIFICATION = "classification"
    DETECTION = "detection"
    SEGMENTATION = "segmentation"
    MULTIMODAL = "multimodal"
    NLP = "nlp"


class Framework(str, Enum):
    """Model framework types"""
    PYTORCH = "pytorch"
    ONNX = "onnx"
    TENSORRT = "tensorrt"


class NetworkType(str, Enum):
    """Model network architecture types"""
    YOLOV8 = "yolov8"
    YOLO11 = "yolo11"


class Model(Base):
    """AI Model database model"""

    __tablename__ = "models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False, index=True)
    description = Column(Text, nullable=True)
    task_type = Column(SQLEnum(TaskType), nullable=False, index=True)
    framework = Column(SQLEnum(Framework), nullable=False, index=True)
    network_type = Column(SQLEnum(NetworkType), nullable=False, index=True)
    input_spec = Column(JSONB, nullable=True)  # e.g., {"image": "HWC", "text": "str"}
    output_spec = Column(JSONB, nullable=True)  # e.g., {"boxes": "Nx4", "labels": "N"}
    version = Column(String(16), default="1.0.0")
    is_public = Column(Boolean, default=False)
    thumbnail_url = Column(Text, nullable=True)
    tags = Column(JSONB, default=list)
    metrics = Column(JSONB, nullable=True)  # Performance metrics
    download_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="models")
    files = relationship("ModelFile", back_populates="model", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Model {self.name}>"


class ModelFile(Base):
    """Model file storage record"""

    __tablename__ = "model_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False)
    file_path = Column(String(256), nullable=False)  # MinIO path
    file_format = Column(String(16), nullable=False)  # 'onnx', 'pt', 'engine'
    file_size = Column(Integer, nullable=True)  # in bytes
    checksum = Column(String(64), nullable=True)  # SHA256
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    model = relationship("Model", back_populates="files")

    def __repr__(self):
        return f"<ModelFile {self.file_path}>"
