"""Triton Model Repository management service

This module handles automatic deployment of uploaded models to Triton Inference Server.
It generates config.pbtxt files and manages model files in the Triton model repository.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException

from app.core.config import settings
from app.core.minio import download_file


class ModelPlatform(str, Enum):
    """Supported Triton model platforms"""
    ONNX = "onnxruntime_onnx"
    TENSORRT = "tensorrt_plan"
    PYTORCH = "pytorch_libtorch"


# Model configuration templates for different network types
YOLO_CONFIG_TEMPLATE = """name: "{model_name}"
platform: "{platform}"
max_batch_size: {max_batch_size}

input [
  {{
    name: "images"
    data_type: TYPE_FP32
    dims: [ 3, {input_height}, {input_width} ]
  }}
]

output [
  {{
    name: "output0"
    data_type: TYPE_FP32
    dims: [ -1, -1 ]
  }}
]

dynamic_batching {{
  preferred_batch_size: [ 1, 2, 4, 8 ]
  max_queue_delay_microseconds: 100
}}

instance_group [
  {{
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }}
]

optimization {{
  cuda {{
    graphs: true
  }}
}}
"""


def get_model_platform(file_format: str) -> ModelPlatform:
    """Get Triton platform based on file format"""
    format_map = {
        "onnx": ModelPlatform.ONNX,
        "engine": ModelPlatform.TENSORRT,
        "trt": ModelPlatform.TENSORRT,
        "pt": ModelPlatform.PYTORCH,
        "pth": ModelPlatform.PYTORCH,
    }
    return format_map.get(file_format.lower(), ModelPlatform.ONNX)


def get_model_filename(file_format: str) -> str:
    """Get expected model filename for Triton"""
    format_map = {
        "onnx": "model.onnx",
        "engine": "model.plan",
        "trt": "model.plan",
        "pt": "model.pt",
        "pth": "model.pt",
    }
    return format_map.get(file_format.lower(), "model.onnx")


class TritonRepositoryManager:
    """Manager for Triton model repository operations"""
    
    def __init__(self, repository_path: str = None, triton_url: str = None):
        self.repository_path = Path(repository_path or settings.TRITON_MODEL_REPOSITORY)
        self.triton_url = triton_url or settings.TRITON_URL
        self._grpc_client = None
    
    @property
    def grpc_client(self) -> grpcclient.InferenceServerClient:
        """Get or create gRPC client for Triton control"""
        if self._grpc_client is None:
            self._grpc_client = grpcclient.InferenceServerClient(
                url=self.triton_url,
                verbose=False,
            )
        return self._grpc_client
    
    def _ensure_repository_exists(self) -> None:
        """Ensure the model repository directory exists"""
        self.repository_path.mkdir(parents=True, exist_ok=True)
    
    def get_model_path(self, model_name: str) -> Path:
        """Get the path for a model in the repository"""
        return self.repository_path / model_name
    
    def get_model_version_path(self, model_name: str, version: int = 1) -> Path:
        """Get the path for a specific model version"""
        return self.get_model_path(model_name) / str(version)
    
    def generate_config(
        self,
        model_name: str,
        network_type: str,
        file_format: str,
        input_size: tuple = (640, 640),
        max_batch_size: int = 8,
    ) -> str:
        """
        Generate config.pbtxt content for a YOLO model
        
        Args:
            model_name: Name of the model in Triton
            network_type: Network type (YOLOv8, YOLO11)
            file_format: Model file format (onnx, engine, etc.)
            input_size: Input image size (width, height)
            max_batch_size: Maximum batch size
            
        Returns:
            config.pbtxt content as string
        """
        platform = get_model_platform(file_format)
        input_width, input_height = input_size
        
        config = YOLO_CONFIG_TEMPLATE.format(
            model_name=model_name,
            platform=platform.value,
            max_batch_size=max_batch_size,
            input_width=input_width,
            input_height=input_height,
        )
        
        return config
    
    async def deploy_model(
        self,
        model_id: str,
        model_name: str,
        network_type: str,
        file_format: str,
        minio_bucket: str,
        minio_object_name: str,
        input_size: tuple = (640, 640),
        version: int = 1,
    ) -> Dict[str, Any]:
        """
        Deploy a model from MinIO to Triton repository
        
        Args:
            model_id: Unique model ID (used as Triton model name)
            model_name: Human-readable model name
            network_type: Network type (YOLOv8, YOLO11)
            file_format: Model file format
            minio_bucket: MinIO bucket containing the model
            minio_object_name: Object name in MinIO
            input_size: Input image size
            version: Model version in Triton
            
        Returns:
            Deployment result with status and path
        """
        self._ensure_repository_exists()
        
        # Use model_id as Triton model name for uniqueness
        triton_model_name = f"model_{model_id}"
        model_path = self.get_model_path(triton_model_name)
        version_path = self.get_model_version_path(triton_model_name, version)
        
        try:
            # Create model directory structure
            version_path.mkdir(parents=True, exist_ok=True)
            
            # Download model from MinIO
            model_data = await download_file(minio_bucket, minio_object_name)
            
            # Write model file with correct name for Triton
            model_filename = get_model_filename(file_format)
            model_file_path = version_path / model_filename
            with open(model_file_path, "wb") as f:
                f.write(model_data)
            
            # Generate and write config.pbtxt
            config_content = self.generate_config(
                model_name=triton_model_name,
                network_type=network_type,
                file_format=file_format,
                input_size=input_size,
            )
            config_path = model_path / "config.pbtxt"
            with open(config_path, "w") as f:
                f.write(config_content)
            
            # Request Triton to load the model
            load_result = await self.load_model(triton_model_name)
            
            return {
                "success": True,
                "triton_model_name": triton_model_name,
                "model_path": str(model_path),
                "config_path": str(config_path),
                "model_file_path": str(model_file_path),
                "triton_loaded": load_result,
            }
            
        except Exception as e:
            # Cleanup on failure
            if model_path.exists():
                shutil.rmtree(model_path, ignore_errors=True)
            
            return {
                "success": False,
                "error": str(e),
                "triton_model_name": triton_model_name,
            }
    
    async def load_model(self, model_name: str) -> bool:
        """
        Request Triton to load a model
        
        Args:
            model_name: Name of the model to load
            
        Returns:
            True if load was successful or model is already loaded
        """
        try:
            # Check if server is available
            if not self.grpc_client.is_server_live():
                print(f"Triton server not available, model {model_name} will be loaded on next restart")
                return False
            
            # Request explicit model load
            self.grpc_client.load_model(model_name)
            
            # Wait briefly and check if model is ready
            import time
            for _ in range(10):  # Try for 5 seconds
                if self.grpc_client.is_model_ready(model_name):
                    print(f"Model {model_name} loaded successfully in Triton")
                    return True
                time.sleep(0.5)
            
            print(f"Model {model_name} load requested but not yet ready")
            return False
            
        except InferenceServerException as e:
            print(f"Failed to load model {model_name} in Triton: {e}")
            return False
    
    async def unload_model(self, model_name: str) -> bool:
        """
        Request Triton to unload a model
        
        Args:
            model_name: Name of the model to unload
            
        Returns:
            True if unload was successful
        """
        try:
            if not self.grpc_client.is_server_live():
                return False
            
            self.grpc_client.unload_model(model_name)
            return True
            
        except InferenceServerException as e:
            print(f"Failed to unload model {model_name}: {e}")
            return False
    
    async def remove_model(self, model_id: str) -> bool:
        """
        Remove a model from Triton repository
        
        Args:
            model_id: Model ID used as Triton model name
            
        Returns:
            True if removal was successful
        """
        triton_model_name = f"model_{model_id}"
        
        # Unload from Triton first
        await self.unload_model(triton_model_name)
        
        # Remove from filesystem
        model_path = self.get_model_path(triton_model_name)
        if model_path.exists():
            try:
                shutil.rmtree(model_path)
                print(f"Removed model {triton_model_name} from repository")
                return True
            except Exception as e:
                print(f"Failed to remove model directory: {e}")
                return False
        
        return True
    
    def is_model_deployed(self, model_id: str) -> bool:
        """Check if a model is deployed in the repository"""
        triton_model_name = f"model_{model_id}"
        model_path = self.get_model_path(triton_model_name)
        config_path = model_path / "config.pbtxt"
        return config_path.exists()
    
    def is_model_ready(self, model_id: str) -> bool:
        """Check if a model is ready in Triton"""
        triton_model_name = f"model_{model_id}"
        try:
            return self.grpc_client.is_model_ready(triton_model_name)
        except InferenceServerException:
            return False
    
    def get_triton_model_name(self, model_id: str) -> str:
        """Get the Triton model name for a given model ID"""
        return f"model_{model_id}"


# Singleton instance
triton_repository = TritonRepositoryManager()
