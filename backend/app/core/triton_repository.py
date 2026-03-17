"""Triton Model Repository management service

This module handles automatic deployment of uploaded models to Triton Inference Server.
It generates config.pbtxt files and manages model files in the Triton model repository.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

import onnx
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException

from app.core.config import settings
from app.core.minio import download_file
from app.core.gpu_manager import gpu_manager

logger = logging.getLogger(__name__)


# OWL model variant configurations
OWL_MODEL_VARIANTS = {
    "owlv2-base-patch16": {
        "image_size": 960,
        "patch_size": 16,
        "num_patches": 3600,
        "trt_shapes": "image:1x3x960x960",
        "image_encoder_triton_name": "owl_image_encoder_base_patch16",
        "text_encoder_triton_name": "owl_text_encoder",
    },
    "owlv2-large-patch14": {
        "image_size": 1008,
        "patch_size": 14,
        "num_patches": 5184,
        "trt_shapes": "image:1x3x1008x1008",
        "image_encoder_triton_name": "owl_image_encoder_large_patch14",
        "text_encoder_triton_name": "owl_text_encoder_large",
    },
}

OWL_TEXT_ENCODER_TRITON_NAME = "owl_text_encoder"


class ModelPlatform(str, Enum):
    """Supported Triton model platforms"""
    ONNX = "onnxruntime_onnx"
    TENSORRT = "tensorrt_plan"
    PYTORCH = "pytorch_libtorch"


# Model configuration template - dynamically generated based on model metadata
# GPU is selected at deployment time based on current load
CONFIG_TEMPLATE = """name: "{model_name}"
platform: "{platform}"
max_batch_size: 0

{inputs_config}

{outputs_config}

instance_group [
  {{
    count: 1
    kind: KIND_GPU
    gpus: [ {gpu_id} ]
  }}
]
"""


def get_onnx_dtype_to_triton(onnx_dtype: int) -> str:
    """Convert ONNX data type to Triton data type string"""
    dtype_map = {
        1: "TYPE_FP32",    # FLOAT
        2: "TYPE_UINT8",   # UINT8
        3: "TYPE_INT8",    # INT8
        4: "TYPE_UINT16",  # UINT16
        5: "TYPE_INT16",   # INT16
        6: "TYPE_INT32",   # INT32
        7: "TYPE_INT64",   # INT64
        9: "TYPE_BOOL",    # BOOL
        10: "TYPE_FP16",   # FLOAT16
        11: "TYPE_FP64",   # DOUBLE
        12: "TYPE_UINT32", # UINT32
        13: "TYPE_UINT64", # UINT64
    }
    return dtype_map.get(onnx_dtype, "TYPE_FP32")


def get_onnx_model_info(model_path: str) -> Dict[str, Any]:
    """
    Extract input/output information from ONNX model
    
    Args:
        model_path: Path to the ONNX model file
        
    Returns:
        Dictionary with inputs and outputs info
    """
    model = onnx.load(model_path)
    graph = model.graph
    
    inputs = []
    for inp in graph.input:
        # Get shape
        shape = []
        for dim in inp.type.tensor_type.shape.dim:
            if dim.dim_value > 0:
                shape.append(dim.dim_value)
            else:
                shape.append(-1)  # Dynamic dimension
        
        inputs.append({
            "name": inp.name,
            "dtype": get_onnx_dtype_to_triton(inp.type.tensor_type.elem_type),
            "dims": shape,
        })
    
    outputs = []
    for out in graph.output:
        shape = []
        for dim in out.type.tensor_type.shape.dim:
            if dim.dim_value > 0:
                shape.append(dim.dim_value)
            else:
                shape.append(-1)
        
        outputs.append({
            "name": out.name,
            "dtype": get_onnx_dtype_to_triton(out.type.tensor_type.elem_type),
            "dims": shape,
        })
    
    return {
        "inputs": inputs,
        "outputs": outputs,
    }


def format_dims(dims: List[int]) -> str:
    """Format dimensions list for config.pbtxt"""
    return "[ " + ", ".join(str(d) for d in dims) + " ]"


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
    
    def generate_config_from_onnx(
        self,
        model_name: str,
        model_path: str,
        file_format: str,
        gpu_id: int = 0,
    ) -> str:
        """
        Generate config.pbtxt content by reading ONNX model metadata
        
        Args:
            model_name: Name of the model in Triton
            model_path: Path to the model file
            file_format: Model file format (onnx, engine, etc.)
            gpu_id: GPU device ID to deploy the model on
            
        Returns:
            config.pbtxt content as string
        """
        platform = get_model_platform(file_format)
        
        # For ONNX models, read the actual input/output shapes
        if file_format.lower() == "onnx":
            model_info = get_onnx_model_info(model_path)
            
            # Build inputs config (use repeated field syntax for protobuf)
            inputs_parts = []
            for inp in model_info["inputs"]:
                inputs_parts.append(
                    f'input {{\n'
                    f'  name: "{inp["name"]}"\n'
                    f'  data_type: {inp["dtype"]}\n'
                    f'  dims: {format_dims(inp["dims"])}\n'
                    f'}}'
                )
            inputs_config = "\n\n".join(inputs_parts)
            
            # Build outputs config (use repeated field syntax for protobuf)
            outputs_parts = []
            for out in model_info["outputs"]:
                outputs_parts.append(
                    f'output {{\n'
                    f'  name: "{out["name"]}"\n'
                    f'  data_type: {out["dtype"]}\n'
                    f'  dims: {format_dims(out["dims"])}\n'
                    f'}}'
                )
            outputs_config = "\n\n".join(outputs_parts)
        else:
            # Default config for non-ONNX models
            inputs_config = '''input {
  name: "images"
  data_type: TYPE_FP32
  dims: [ 1, 3, 640, 640 ]
}'''
            outputs_config = '''output {
  name: "output0"
  data_type: TYPE_FP32
  dims: [ -1, -1 ]
}'''
        
        config = CONFIG_TEMPLATE.format(
            model_name=model_name,
            platform=platform.value,
            inputs_config=inputs_config,
            outputs_config=outputs_config,
            gpu_id=gpu_id,
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
        version: int = 1,
        gpu_id: Optional[int] = None,
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
            version: Model version in Triton
            gpu_id: Specific GPU to deploy on (None for auto-selection)
            
        Returns:
            Deployment result with status and path
        """
        self._ensure_repository_exists()
        
        # Use model_id as Triton model name for uniqueness
        triton_model_name = f"model_{model_id}"
        model_path = self.get_model_path(triton_model_name)
        version_path = self.get_model_version_path(triton_model_name, version)
        
        # Select optimal GPU if not specified
        selected_gpu = gpu_id
        gpu_info = None
        if selected_gpu is None:
            selected_gpu, gpu_info = gpu_manager.select_optimal_gpu()
            logger.info(f"Auto-selected GPU {selected_gpu} for model {model_name}")
        
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
            
            # Generate config.pbtxt by reading model metadata
            config_content = self.generate_config_from_onnx(
                model_name=triton_model_name,
                model_path=str(model_file_path),
                file_format=file_format,
                gpu_id=selected_gpu,
            )
            config_path = model_path / "config.pbtxt"
            with open(config_path, "w") as f:
                f.write(config_content)
            
            # Request Triton to load the model
            load_result = await self.load_model(triton_model_name)
            
            result = {
                "success": True,
                "triton_model_name": triton_model_name,
                "model_path": str(model_path),
                "config_path": str(config_path),
                "model_file_path": str(model_file_path),
                "triton_loaded": load_result,
                "gpu_id": selected_gpu,
            }
            
            # Add GPU info if available
            if gpu_info:
                result["gpu_info"] = {
                    "name": gpu_info.name,
                    "memory_usage_percent": round(gpu_info.memory_usage_percent, 1),
                    "gpu_utilization": round(gpu_info.gpu_utilization, 1),
                }
            
            return result
            
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
        import time
        
        try:
            # Check if server is available
            if not self.grpc_client.is_server_live():
                print(f"Triton server not available, model {model_name} will be loaded on next restart")
                return False
            
            # Check if model is already ready
            if self.grpc_client.is_model_ready(model_name):
                print(f"Model {model_name} is already loaded in Triton")
                return True
            
            # Try explicit model load (may fail if polling is enabled)
            try:
                self.grpc_client.load_model(model_name)
            except InferenceServerException as e:
                if "polling is enabled" in str(e):
                    # Polling mode: Triton will auto-load, just wait for it
                    print(f"Triton is in polling mode, waiting for auto-load of {model_name}")
                else:
                    raise
            
            # Wait for model to be ready (works for both explicit and polling mode)
            for _ in range(20):  # Try for 10 seconds
                if self.grpc_client.is_model_ready(model_name):
                    print(f"Model {model_name} loaded successfully in Triton")
                    return True
                time.sleep(0.5)
            
            print(f"Model {model_name} deployed but not yet ready (Triton may still be loading)")
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
    
    def is_model_deployed(self, model_id: str, network_type: str = "") -> bool:
        """Check if a model is deployed in the repository"""
        if network_type == "OWLv2":
            # OWL models use fixed Triton names, check any variant
            for vc in OWL_MODEL_VARIANTS.values():
                te_name = vc["text_encoder_triton_name"]
                ie_name = vc["image_encoder_triton_name"]
                te_config = self.get_model_path(te_name) / "config.pbtxt"
                ie_config = self.get_model_path(ie_name) / "config.pbtxt"
                if te_config.exists() and ie_config.exists():
                    return True
            return False
        triton_model_name = f"model_{model_id}"
        model_path = self.get_model_path(triton_model_name)
        config_path = model_path / "config.pbtxt"
        return config_path.exists()
    
    def is_model_ready(self, model_id: str, network_type: str = "") -> bool:
        """Check if a model is ready in Triton"""
        if network_type == "OWLv2":
            # OWL models: check if at least one variant pair is ready
            for vc in OWL_MODEL_VARIANTS.values():
                te_name = vc["text_encoder_triton_name"]
                ie_name = vc["image_encoder_triton_name"]
                try:
                    if (self.grpc_client.is_model_ready(te_name)
                            and self.grpc_client.is_model_ready(ie_name)):
                        return True
                except InferenceServerException:
                    continue
            return False
        triton_model_name = f"model_{model_id}"
        try:
            return self.grpc_client.is_model_ready(triton_model_name)
        except InferenceServerException:
            return False
    
    def is_model_loaded(self, triton_model_name: str) -> bool:
        """Check if a model is loaded in Triton by its Triton model name"""
        try:
            return self.grpc_client.is_model_ready(triton_model_name)
        except InferenceServerException:
            return False
    
    def get_triton_model_name(self, model_id: str) -> str:
        """Get the Triton model name for a given model ID"""
        return f"model_{model_id}"
    
    def get_model_gpu_id(self, model_id: str) -> Optional[int]:
        """
        Get the GPU ID that a model is deployed on by reading config.pbtxt
        
        Args:
            model_id: Model ID
            
        Returns:
            GPU ID or None if not found
        """
        import re
        
        triton_model_name = f"model_{model_id}"
        config_path = self.get_model_path(triton_model_name) / "config.pbtxt"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r") as f:
                config_content = f.read()
            
            # Parse gpus: [ X ] from config
            match = re.search(r'gpus:\s*\[\s*(\d+)\s*\]', config_content)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            logger.error(f"Failed to read GPU ID from config: {e}")
            return None
    
    def get_gpus_status(self) -> dict:
        """Get current GPU status summary"""
        return gpu_manager.get_gpus_status_summary()
    
    async def redeploy_model_to_gpu(
        self,
        model_id: str,
        gpu_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Redeploy an existing model to a different GPU (or auto-select optimal GPU)
        
        Args:
            model_id: Model ID to redeploy
            gpu_id: Target GPU ID (None for auto-selection)
            
        Returns:
            Result dict with success status
        """
        triton_model_name = f"model_{model_id}"
        model_path = self.get_model_path(triton_model_name)
        config_path = model_path / "config.pbtxt"
        
        if not config_path.exists():
            return {
                "success": False,
                "error": f"Model {model_id} not found in repository",
            }
        
        # Select optimal GPU if not specified
        selected_gpu = gpu_id
        gpu_info = None
        if selected_gpu is None:
            selected_gpu, gpu_info = gpu_manager.select_optimal_gpu()
            logger.info(f"Auto-selected GPU {selected_gpu} for model redeployment")
        
        try:
            # Read current config
            with open(config_path, "r") as f:
                config_content = f.read()
            
            # Update GPU ID in config
            import re
            new_config = re.sub(
                r'gpus:\s*\[\s*\d+\s*\]',
                f'gpus: [ {selected_gpu} ]',
                config_content
            )
            
            # Write updated config
            with open(config_path, "w") as f:
                f.write(new_config)
            
            # Unload and reload model
            await self.unload_model(triton_model_name)
            load_result = await self.load_model(triton_model_name)
            
            result = {
                "success": True,
                "model_id": model_id,
                "gpu_id": selected_gpu,
                "triton_loaded": load_result,
            }
            
            if gpu_info:
                result["gpu_info"] = {
                    "name": gpu_info.name,
                    "memory_usage_percent": round(gpu_info.memory_usage_percent, 1),
                    "gpu_utilization": round(gpu_info.gpu_utilization, 1),
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to redeploy model {model_id}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def load_all_deployed_models(self) -> dict:
        """
        Load all models that are deployed in the repository.
        Called on application startup to ensure all models are loaded in Triton.
        
        Returns:
            Dictionary with loaded and failed model lists
        """
        loaded = []
        failed = []
        
        try:
            # Check if Triton server is available
            if not self.grpc_client.is_server_live():
                print("Triton server not available, skipping model loading")
                return {"loaded": loaded, "failed": failed, "error": "Triton server not available"}
            
            # Get all model directories in the repository
            if not self.repository_path.exists():
                print(f"Model repository path does not exist: {self.repository_path}")
                return {"loaded": loaded, "failed": failed}
            
            for model_dir in self.repository_path.iterdir():
                if model_dir.is_dir() and model_dir.name.startswith("model_"):
                    model_name = model_dir.name
                    config_path = model_dir / "config.pbtxt"
                    
                    # Only try to load if config exists
                    if config_path.exists():
                        try:
                            result = await self.load_model(model_name)
                            if result:
                                loaded.append(model_name)
                                print(f"Loaded model: {model_name}")
                            else:
                                failed.append(model_name)
                                print(f"Failed to load model: {model_name}")
                        except Exception as e:
                            failed.append(model_name)
                            print(f"Error loading model {model_name}: {e}")
                    else:
                        print(f"Skipping {model_name}: no config.pbtxt found")
            
            print(f"Model loading complete: {len(loaded)} loaded, {len(failed)} failed")
            return {"loaded": loaded, "failed": failed}
            
        except Exception as e:
            print(f"Error during model loading: {e}")
            return {"loaded": loaded, "failed": failed, "error": str(e)}

    def generate_config_for_engine(
        self,
        model_name: str,
        onnx_source_path: str,
        gpu_id: int = 0,
    ) -> str:
        """
        Generate config.pbtxt for a TensorRT engine model.
        
        Reads IO metadata from the source ONNX file but uses tensorrt_plan platform.
        
        Args:
            model_name: Name of the model in Triton
            onnx_source_path: Path to the source ONNX file (for metadata extraction)
            gpu_id: GPU device ID
            
        Returns:
            config.pbtxt content as string
        """
        model_info = get_onnx_model_info(onnx_source_path)
        
        inputs_parts = []
        for inp in model_info["inputs"]:
            inputs_parts.append(
                f'input {{\n'
                f'  name: "{inp["name"]}"\n'
                f'  data_type: {inp["dtype"]}\n'
                f'  dims: {format_dims(inp["dims"])}\n'
                f'}}'
            )
        inputs_config = "\n\n".join(inputs_parts)
        
        outputs_parts = []
        for out in model_info["outputs"]:
            outputs_parts.append(
                f'output {{\n'
                f'  name: "{out["name"]}"\n'
                f'  data_type: {out["dtype"]}\n'
                f'  dims: {format_dims(out["dims"])}\n'
                f'}}'
            )
        outputs_config = "\n\n".join(outputs_parts)
        
        config = CONFIG_TEMPLATE.format(
            model_name=model_name,
            platform=ModelPlatform.TENSORRT.value,
            inputs_config=inputs_config,
            outputs_config=outputs_config,
            gpu_id=gpu_id,
        )
        
        return config

    async def deploy_owl_text_encoder(
        self,
        variant: str = "owlv2-base-patch16",
        onnx_source_path: Optional[str] = None,
        gpu_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Deploy the OWL text encoder (ONNX) to Triton.
        
        Each variant has its own text encoder with different embedding
        dimensions (base=512, large=768).
        
        Args:
            variant: Model variant key, determines Triton model name and
                     fallback ONNX source path.
            onnx_source_path: Path to user-uploaded ONNX file. Falls back to settings if None.
            gpu_id: Target GPU ID (None for auto-selection)
        """
        variant_config = OWL_MODEL_VARIANTS.get(variant)
        if not variant_config:
            return {"success": False, "error": f"Unknown OWL variant: {variant}"}

        model_name = variant_config["text_encoder_triton_name"]
        model_path = self.get_model_path(model_name)
        version_path = self.get_model_version_path(model_name, 1)
        
        # Step 1: Skip if already deployed and ready
        try:
            if self.grpc_client.is_server_live() and self.grpc_client.is_model_ready(model_name):
                logger.info(f"OWL text encoder ({variant}) already loaded in Triton")
                return {"success": True, "triton_model_name": model_name, "already_loaded": True}
        except InferenceServerException:
            pass
        
        # Step 2: If model files already exist in the repository (from a
        # previous upload via /owl-files), just load them into Triton.
        existing_model_file = version_path / "model.onnx"
        existing_config = model_path / "config.pbtxt"
        if existing_model_file.exists() and existing_config.exists():
            try:
                load_result = await self.load_model(model_name)
                logger.info(f"OWL text encoder ({variant}) loaded from existing repository: {load_result}")
                return {"success": True, "triton_model_name": model_name, "loaded_from_repo": True}
            except Exception as e:
                logger.warning(f"Failed to load existing OWL text encoder ({variant}): {e}, will try re-deploy")
        
        # Step 3: Deploy from source ONNX
        if onnx_source_path:
            onnx_source = onnx_source_path
        elif variant == "owlv2-large-patch14":
            onnx_source = settings.OWL_TEXT_ENCODER_ONNX_LARGE
        else:
            onnx_source = settings.OWL_TEXT_ENCODER_ONNX

        if not onnx_source or not os.path.exists(onnx_source):
            return {"success": False, "error": f"Text encoder ONNX not found for {variant}: {onnx_source}"}
        
        selected_gpu = gpu_id
        if selected_gpu is None:
            selected_gpu, _ = gpu_manager.select_optimal_gpu()
        
        try:
            version_path.mkdir(parents=True, exist_ok=True)
            
            # Place ONNX file in model directory
            model_file = version_path / "model.onnx"
            if model_file.exists() or model_file.is_symlink():
                model_file.unlink()
            if onnx_source_path:
                # User-uploaded file: copy to model dir (symlink won't work
                # across containers since /tmp is not shared with Triton)
                import shutil
                shutil.copy2(onnx_source, str(model_file))
            else:
                # Config-based permanent path: symlink is fine
                model_file.symlink_to(onnx_source)
            
            # Generate minimal config - let Triton auto-detect I/O shapes
            # from the ONNX model (requires strict-model-config=false).
            # Using 'backend' instead of 'platform' for Triton >= 24.xx.
            config_content = (
                f'name: "{model_name}"\n'
                f'backend: "onnxruntime"\n'
                f'max_batch_size: 0\n'
                f'instance_group [\n'
                f'  {{\n'
                f'    count: 1\n'
                f'    kind: KIND_GPU\n'
                f'    gpus: [ {selected_gpu} ]\n'
                f'  }}\n'
                f']\n'
            )
            config_path = model_path / "config.pbtxt"
            with open(config_path, "w") as f:
                f.write(config_content)
            
            load_result = await self.load_model(model_name)
            logger.info(f"OWL text encoder ({variant}) deployed: loaded={load_result}")
            
            return {
                "success": True,
                "triton_model_name": model_name,
                "triton_loaded": load_result,
                "gpu_id": selected_gpu,
            }
        except Exception as e:
            logger.exception(f"Failed to deploy OWL text encoder ({variant}): {e}")
            return {"success": False, "error": str(e)}

    async def deploy_owl_image_encoder(
        self,
        variant: str,
        onnx_source_path: Optional[str] = None,
        gpu_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Deploy the OWL image encoder to Triton.
        
        If no pre-built TensorRT engine exists, automatically converts from ONNX
        using trtexec. Then deploys the engine with tensorrt_plan platform.
        
        Args:
            variant: Model variant key, e.g. "owlv2-base-patch16"
            onnx_source_path: Path to user-uploaded ONNX file. Falls back to settings if None.
            gpu_id: Target GPU ID (None for auto-selection)
        """
        from app.core.tensorrt_converter import tensorrt_converter
        
        variant_config = OWL_MODEL_VARIANTS.get(variant)
        if not variant_config:
            return {"success": False, "error": f"Unknown OWL variant: {variant}"}
        
        model_name = variant_config["image_encoder_triton_name"]
        model_path = self.get_model_path(model_name)
        version_path = self.get_model_version_path(model_name, 1)
        
        # Step 1: Skip if already deployed and ready
        try:
            if self.grpc_client.is_server_live() and self.grpc_client.is_model_ready(model_name):
                logger.info(f"OWL image encoder ({variant}) already loaded in Triton")
                return {"success": True, "triton_model_name": model_name, "already_loaded": True}
        except InferenceServerException:
            pass
        
        # Step 2: If TRT engine + config already exist in the repository (from
        # a previous upload via /owl-files), just load them into Triton.
        existing_engine = version_path / "model.plan"
        existing_config = model_path / "config.pbtxt"
        if existing_engine.exists() and existing_config.exists():
            try:
                load_result = await self.load_model(model_name)
                logger.info(f"OWL image encoder ({variant}) loaded from existing repository: {load_result}")
                return {"success": True, "triton_model_name": model_name, "loaded_from_repo": True}
            except Exception as e:
                logger.warning(f"Failed to load existing OWL image encoder ({variant}): {e}, will try re-deploy")
        
        # Step 3: Deploy from source ONNX
        # Determine ONNX source path
        if onnx_source_path:
            onnx_source = onnx_source_path
        elif variant == "owlv2-base-patch16":
            onnx_source = settings.OWL_IMAGE_ENCODER_ONNX_BASE
        elif variant == "owlv2-large-patch14":
            onnx_source = settings.OWL_IMAGE_ENCODER_ONNX_LARGE
        else:
            return {"success": False, "error": f"No ONNX path configured for variant: {variant}"}
        
        if not onnx_source or not os.path.exists(onnx_source):
            return {"success": False, "error": f"Image encoder ONNX not found: {onnx_source}"}
        
        selected_gpu = gpu_id
        if selected_gpu is None:
            selected_gpu, _ = gpu_manager.select_optimal_gpu()
        
        try:
            version_path.mkdir(parents=True, exist_ok=True)
            engine_file = version_path / "model.plan"
            
            # If source ONNX is outside model repository (e.g. /tmp from upload),
            # copy it into the repo so the Triton container can access it for
            # trtexec conversion (Triton only sees the shared /models volume).
            onnx_for_conversion = onnx_source
            staged_onnx = None
            if not str(onnx_source).startswith(str(self.repository_path)):
                import shutil
                staged_onnx = version_path / "source.onnx"
                shutil.copy2(onnx_source, str(staged_onnx))
                onnx_for_conversion = str(staged_onnx)
            
            # Convert ONNX to TensorRT engine if needed
            if not engine_file.exists():
                logger.info(f"Converting OWL image encoder ONNX to TensorRT engine ({variant})...")
                
                convert_result = await tensorrt_converter.convert_onnx_to_tensorrt(
                    onnx_path=onnx_for_conversion,
                    output_path=str(engine_file),
                    fp16=True,
                    shapes=variant_config["trt_shapes"],
                )
                
                if not convert_result.get("success"):
                    return {
                        "success": False,
                        "error": f"TensorRT conversion failed: {convert_result.get('error', 'unknown')}",
                        "details": convert_result.get("details", ""),
                    }
                
                logger.info(f"TensorRT conversion completed for {variant}")
            
            # Clean up staged ONNX (only the .plan is needed for Triton)
            if staged_onnx and staged_onnx.exists():
                staged_onnx.unlink()
            
            # Generate config.pbtxt from ONNX metadata but with tensorrt_plan platform
            config_content = self.generate_config_for_engine(
                model_name=model_name,
                onnx_source_path=onnx_source,
                gpu_id=selected_gpu,
            )
            config_path = model_path / "config.pbtxt"
            with open(config_path, "w") as f:
                f.write(config_content)
            
            load_result = await self.load_model(model_name)
            logger.info(f"OWL image encoder ({variant}) deployed: loaded={load_result}")
            
            return {
                "success": True,
                "triton_model_name": model_name,
                "triton_loaded": load_result,
                "gpu_id": selected_gpu,
            }
        except Exception as e:
            logger.exception(f"Failed to deploy OWL image encoder ({variant}): {e}")
            return {"success": False, "error": str(e)}

    async def deploy_owl_models(
        self,
        variant: str = "owlv2-base-patch16",
        text_encoder_path: Optional[str] = None,
        image_encoder_path: Optional[str] = None,
        gpu_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Deploy both OWL text encoder and image encoder(s) to Triton.
        
        Deploys the text encoder and the specified image encoder variant.
        Also attempts to load any other variants (both text and image
        encoders) that already exist in the repository.
        
        Args:
            variant: Model variant key to deploy
            text_encoder_path: Path to user-uploaded text encoder ONNX. Falls back to settings if None.
            image_encoder_path: Path to user-uploaded image encoder ONNX. Falls back to settings if None.
            gpu_id: Target GPU ID (None for auto-selection)
            
        Returns:
            Combined deployment result
        """
        text_result = await self.deploy_owl_text_encoder(
            variant=variant, onnx_source_path=text_encoder_path, gpu_id=gpu_id,
        )
        image_result = await self.deploy_owl_image_encoder(
            variant=variant, onnx_source_path=image_encoder_path, gpu_id=gpu_id,
        )
        
        # Also try loading other variants (text + image encoders) from existing repo
        other_results = {}
        for other_variant in OWL_MODEL_VARIANTS:
            if other_variant != variant:
                try:
                    tr = await self.deploy_owl_text_encoder(
                        variant=other_variant, gpu_id=gpu_id,
                    )
                    if tr.get("success"):
                        other_results[f"{other_variant}_text"] = tr
                except Exception:
                    pass
                try:
                    ir = await self.deploy_owl_image_encoder(
                        variant=other_variant, gpu_id=gpu_id,
                    )
                    if ir.get("success"):
                        other_results[f"{other_variant}_image"] = ir
                except Exception:
                    pass
        
        return {
            "success": text_result.get("success", False) and image_result.get("success", False),
            "text_encoder": text_result,
            "image_encoder": image_result,
            "other_variants": other_results,
        }


# Singleton instance
triton_repository = TritonRepositoryManager()
