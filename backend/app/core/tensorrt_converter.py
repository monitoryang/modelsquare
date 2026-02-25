"""TensorRT model conversion service

Converts ONNX models to TensorRT engine files using trtexec in the Triton container.
Supports FP16 precision and progress tracking via callbacks.
"""

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class TensorRTConverter:
    """Handles ONNX to TensorRT conversion using trtexec"""
    
    def __init__(
        self,
        triton_container: str = "modelsquare-triton",
        model_repository: str = None,
    ):
        self.triton_container = triton_container
        self.model_repository = Path(model_repository or settings.TRITON_MODEL_REPOSITORY)
    
    async def convert_onnx_to_tensorrt(
        self,
        onnx_path: str,
        output_path: str,
        fp16: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Convert ONNX model to TensorRT engine using trtexec in Triton container.
        
        Args:
            onnx_path: Path to ONNX file (relative to model repository or absolute)
            output_path: Output path for .engine file
            fp16: Enable FP16 precision
            progress_callback: Callback function(progress: int, message: str)
            
        Returns:
            Dict with success status and error message if failed
        """
        # Resolve paths relative to model repository
        onnx_full_path = Path(onnx_path)
        output_full_path = Path(output_path)
        
        # Convert to container paths (mounted at /models)
        try:
            onnx_container_path = "/models" / onnx_full_path.relative_to(self.model_repository)
            output_container_path = "/models" / output_full_path.relative_to(self.model_repository)
        except ValueError:
            # Already absolute paths, try to use as-is
            onnx_container_path = onnx_full_path
            output_container_path = output_full_path
        
        # Build trtexec command
        cmd = [
            "docker", "exec", self.triton_container,
            "/usr/src/tensorrt/bin/trtexec",
            f"--onnx={onnx_container_path}",
            f"--saveEngine={output_container_path}",
            "--verbose",
        ]
        
        if fp16:
            cmd.append("--fp16")
        
        if progress_callback:
            progress_callback(0, "Starting TensorRT conversion...")
        
        logger.info(f"Running TensorRT conversion: {' '.join(cmd)}")
        
        try:
            # Run conversion with progress tracking
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            
            output_lines = []
            current_progress = 0
            
            async for line in process.stdout:
                line_text = line.decode('utf-8', errors='ignore').strip()
                output_lines.append(line_text)
                
                # Parse progress from trtexec output
                new_progress, message = self._parse_progress(line_text, current_progress)
                if new_progress > current_progress:
                    current_progress = new_progress
                    if progress_callback:
                        progress_callback(current_progress, message)
            
            await process.wait()
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "Conversion completed successfully")
                
                return {
                    "success": True,
                    "output_path": str(output_full_path),
                    "message": "Conversion completed successfully",
                }
            else:
                error_msg = "\n".join(output_lines[-10:])  # Last 10 lines
                logger.error(f"TensorRT conversion failed: {error_msg}")
                
                return {
                    "success": False,
                    "error": f"Conversion failed with exit code {process.returncode}",
                    "details": error_msg,
                }
                
        except Exception as e:
            logger.exception(f"TensorRT conversion error: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def _parse_progress(self, line: str, current_progress: int) -> tuple[int, str]:
        """
        Parse trtexec output to estimate conversion progress.
        
        trtexec doesn't have explicit progress, so we estimate based on phases:
        - Parsing ONNX: 0-10%
        - Building network: 10-30%
        - Optimization: 30-80%
        - Serializing engine: 80-95%
        - Complete: 100%
        """
        line_lower = line.lower()
        
        # Phase detection
        if "parsing network" in line_lower or "parsing onnx" in line_lower:
            return max(5, current_progress), "Parsing ONNX model..."
        
        if "building tensorrt network" in line_lower or "building engine" in line_lower:
            return max(15, current_progress), "Building TensorRT network..."
        
        if "starting optimization" in line_lower:
            return max(30, current_progress), "Optimizing network..."
        
        # Timing/profiling phases indicate optimization progress
        if "tactic" in line_lower:
            # Increment progress during optimization
            new_progress = min(current_progress + 1, 75)
            return new_progress, "Optimizing layers..."
        
        if "selecting" in line_lower and "kernel" in line_lower:
            return max(60, current_progress), "Selecting optimal kernels..."
        
        if "selected" in line_lower and "tactic" in line_lower:
            return max(70, current_progress), "Finalizing optimization..."
        
        if "serializing" in line_lower or "writing" in line_lower:
            return max(85, current_progress), "Serializing engine..."
        
        if "engine built" in line_lower or "engine generated" in line_lower:
            return 95, "Engine built, finalizing..."
        
        if "successfully" in line_lower and ("saved" in line_lower or "created" in line_lower):
            return 98, "Saving engine file..."
        
        return current_progress, ""
    
    def check_trtexec_available(self) -> bool:
        """Check if trtexec is available in the Triton container"""
        try:
            result = subprocess.run(
                ["docker", "exec", self.triton_container, "which", "trtexec"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False


# Singleton instance
tensorrt_converter = TensorRTConverter()
