"""GPU Management Service for automatic load balancing

This module provides GPU monitoring and selection functionality.
It queries GPU status and selects the optimal GPU based on memory usage and utilization.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """GPU status information"""
    index: int
    name: str
    memory_total: int  # bytes
    memory_used: int   # bytes
    memory_free: int   # bytes
    memory_usage_percent: float
    gpu_utilization: float  # 0-100
    is_available: bool = True
    
    @property
    def load_score(self) -> float:
        """
        Calculate a load score for GPU selection (lower is better).
        Combines memory usage and GPU utilization.
        Memory is weighted more heavily as it's the primary constraint for model loading.
        """
        # 70% weight on memory usage, 30% on GPU utilization
        return self.memory_usage_percent * 0.7 + self.gpu_utilization * 0.3


class GPUManager:
    """Manager for GPU monitoring and selection"""
    
    def __init__(self):
        self._nvml_initialized = False
        self._pynvml = None
        self._init_nvml()
    
    def _init_nvml(self) -> bool:
        """Initialize NVML library"""
        if self._nvml_initialized:
            return True
        
        try:
            import pynvml
            pynvml.nvmlInit()
            self._pynvml = pynvml
            self._nvml_initialized = True
            logger.info("NVML initialized successfully")
            return True
        except ImportError:
            logger.warning("pynvml not installed. GPU monitoring disabled.")
            return False
        except Exception as e:
            logger.warning(f"Failed to initialize NVML: {e}. GPU monitoring disabled.")
            return False
    
    def _ensure_nvml(self) -> bool:
        """Ensure NVML is initialized"""
        if not self._nvml_initialized:
            return self._init_nvml()
        return True
    
    def get_gpu_count(self) -> int:
        """Get the number of available GPUs"""
        if not self._ensure_nvml():
            return 0
        
        try:
            return self._pynvml.nvmlDeviceGetCount()
        except Exception as e:
            logger.error(f"Failed to get GPU count: {e}")
            return 0
    
    def get_gpu_info(self, gpu_index: int) -> Optional[GPUInfo]:
        """Get detailed information for a specific GPU"""
        if not self._ensure_nvml():
            return None
        
        try:
            handle = self._pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            
            # Get GPU name
            name = self._pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            
            # Get memory info
            memory_info = self._pynvml.nvmlDeviceGetMemoryInfo(handle)
            memory_total = memory_info.total
            memory_used = memory_info.used
            memory_free = memory_info.free
            memory_usage_percent = (memory_used / memory_total) * 100 if memory_total > 0 else 0
            
            # Get GPU utilization
            utilization = self._pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_utilization = utilization.gpu
            
            return GPUInfo(
                index=gpu_index,
                name=name,
                memory_total=memory_total,
                memory_used=memory_used,
                memory_free=memory_free,
                memory_usage_percent=memory_usage_percent,
                gpu_utilization=gpu_utilization,
                is_available=True,
            )
        except Exception as e:
            logger.error(f"Failed to get GPU {gpu_index} info: {e}")
            return None
    
    def get_all_gpus_info(self) -> List[GPUInfo]:
        """Get information for all available GPUs"""
        gpu_count = self.get_gpu_count()
        gpus = []
        
        for i in range(gpu_count):
            gpu_info = self.get_gpu_info(i)
            if gpu_info:
                gpus.append(gpu_info)
        
        return gpus
    
    def select_optimal_gpu(
        self,
        required_memory_mb: Optional[int] = None,
        exclude_gpus: Optional[List[int]] = None,
    ) -> Tuple[int, Optional[GPUInfo]]:
        """
        Select the optimal GPU based on current load.
        
        Args:
            required_memory_mb: Minimum required free memory in MB (optional)
            exclude_gpus: List of GPU indices to exclude from selection
        
        Returns:
            Tuple of (selected_gpu_index, gpu_info)
            Returns (0, None) as fallback if no GPUs available or monitoring disabled
        """
        if not self._ensure_nvml():
            logger.warning("NVML not available, defaulting to GPU 0")
            return (0, None)
        
        gpus = self.get_all_gpus_info()
        
        if not gpus:
            logger.warning("No GPUs found, defaulting to GPU 0")
            return (0, None)
        
        # Filter out excluded GPUs
        if exclude_gpus:
            gpus = [g for g in gpus if g.index not in exclude_gpus]
        
        if not gpus:
            logger.warning("All GPUs excluded, defaulting to GPU 0")
            return (0, None)
        
        # Filter by required memory if specified
        if required_memory_mb:
            required_memory_bytes = required_memory_mb * 1024 * 1024
            gpus = [g for g in gpus if g.memory_free >= required_memory_bytes]
            
            if not gpus:
                logger.warning(f"No GPU with {required_memory_mb}MB free memory, defaulting to GPU 0")
                return (0, None)
        
        # Sort by load score (lower is better)
        gpus.sort(key=lambda g: g.load_score)
        
        selected = gpus[0]
        logger.info(
            f"Selected GPU {selected.index} ({selected.name}): "
            f"memory={selected.memory_usage_percent:.1f}%, "
            f"utilization={selected.gpu_utilization:.1f}%, "
            f"load_score={selected.load_score:.1f}"
        )
        
        return (selected.index, selected)
    
    def get_gpus_status_summary(self) -> dict:
        """Get a summary of all GPUs status for API response"""
        gpus = self.get_all_gpus_info()
        
        return {
            "gpu_count": len(gpus),
            "gpus": [
                {
                    "index": g.index,
                    "name": g.name,
                    "memory_total_gb": round(g.memory_total / (1024**3), 2),
                    "memory_used_gb": round(g.memory_used / (1024**3), 2),
                    "memory_free_gb": round(g.memory_free / (1024**3), 2),
                    "memory_usage_percent": round(g.memory_usage_percent, 1),
                    "gpu_utilization": round(g.gpu_utilization, 1),
                    "load_score": round(g.load_score, 1),
                }
                for g in gpus
            ],
            "monitoring_available": self._nvml_initialized,
        }
    
    def shutdown(self):
        """Shutdown NVML"""
        if self._nvml_initialized and self._pynvml:
            try:
                self._pynvml.nvmlShutdown()
                self._nvml_initialized = False
                logger.info("NVML shutdown successfully")
            except Exception as e:
                logger.warning(f"Failed to shutdown NVML: {e}")


# Singleton instance
gpu_manager = GPUManager()
