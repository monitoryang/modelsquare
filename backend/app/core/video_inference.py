"""Video inference service using FFmpeg for decoding and Triton for inference"""

import asyncio
import io
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.core.minio import get_minio_client, upload_file
from app.core.redis import get_redis
from app.core.triton import yolo_inference_service
from app.core.triton_repository import triton_repository
from app.schemas.inference import VideoTaskStatus


# Maximum video size: 2GB
MAX_VIDEO_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes
# Maximum video duration: 10 minutes
MAX_VIDEO_DURATION = 10 * 60  # 600 seconds


class VideoInferenceService:
    """Service for video inference with FFmpeg and Triton"""
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
    
    async def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Get video information using FFprobe"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"FFprobe failed: {stderr.decode()}")
        
        info = json.loads(stdout.decode())
        
        # Extract relevant info
        video_stream = None
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        
        if not video_stream:
            raise ValueError("No video stream found")
        
        # Calculate FPS
        fps_str = video_stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den != 0 else 30.0
        else:
            fps = float(fps_str)
        
        # Get duration
        duration = float(info.get("format", {}).get("duration", 0))
        if duration == 0 and "duration" in video_stream:
            duration = float(video_stream["duration"])
        
        # Calculate total frames
        nb_frames = video_stream.get("nb_frames")
        if nb_frames:
            total_frames = int(nb_frames)
        else:
            total_frames = int(duration * fps)
        
        return {
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": fps,
            "duration": duration,
            "total_frames": total_frames,
            "codec": video_stream.get("codec_name", "unknown"),
        }
    
    async def extract_frames(
        self,
        video_path: str,
        output_dir: str,
        fps: Optional[float] = None
    ) -> List[str]:
        """Extract frames from video using FFmpeg"""
        os.makedirs(output_dir, exist_ok=True)
        
        cmd = [
            "ffmpeg",
            "-i", video_path,
        ]
        
        # Use video filter for frame rate instead of -r to avoid conflicts
        if fps:
            cmd.extend(["-vf", f"fps={fps}"])
        
        cmd.extend([
            "-q:v", "2",
            f"{output_dir}/frame_%06d.jpg"
        ])
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg frame extraction failed: {stderr.decode()}")
        
        # Get list of extracted frames
        frames = sorted([
            os.path.join(output_dir, f) 
            for f in os.listdir(output_dir) 
            if f.startswith("frame_") and f.endswith(".jpg")
        ])
        
        return frames
    
    async def infer_frame(
        self,
        frame_path: str,
        model_name: str,
        class_names: Optional[List[str]],
        conf_threshold: float,
        iou_threshold: float
    ) -> Dict[str, Any]:
        """Run inference on a single frame"""
        with open(frame_path, "rb") as f:
            image_bytes = f.read()
        
        result = await yolo_inference_service.infer(
            model_name=model_name,
            image_bytes=image_bytes,
            class_names=class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold
        )
        
        return result
    
    def draw_detections_on_frame(
        self,
        frame_path: str,
        output_path: str,
        detection_result: Dict[str, Any],
        class_colors: Optional[Dict[str, str]],
        line_width: int = 2,
        font_size: int = 14
    ) -> None:
        """Draw detection boxes on a frame and save"""
        image = Image.open(frame_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        draw = ImageDraw.Draw(image)
        
        # Try Chinese font first, then fallback to DejaVu, then default
        font = None
        font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",  # Chinese support
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
        class_names_list = detection_result.get("class_names", [])
        
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box
            class_name = class_names_list[i] if i < len(class_names_list) else f"class_{i}"
            score = scores[i] if i < len(scores) else 0.0
            
            # Get color
            color_hex = "#FF0000"
            if class_colors and class_name in class_colors:
                color_hex = class_colors[class_name]
            
            color = self._hex_to_rgb(color_hex)
            
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
        
        image.save(output_path, "JPEG", quality=95)
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    async def render_video(
        self,
        frames_dir: str,
        output_path: str,
        fps: float
    ) -> None:
        """Render frames back to video using FFmpeg"""
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate", str(fps),
            "-i", f"{frames_dir}/rendered_%06d.jpg",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "23",
            output_path
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg video render failed: {stderr.decode()}")
    
    async def update_task_status(
        self,
        task_id: str,
        status: VideoTaskStatus,
        progress_data: Dict[str, Any]
    ) -> None:
        """Update task status in Redis"""
        redis = await get_redis()
        key = f"video_task:{task_id}"
        
        task_data = {
            "task_id": task_id,
            "status": status.value,
            **progress_data,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await redis.set(key, json.dumps(task_data), ex=86400)  # 24 hour TTL
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status from Redis"""
        redis = await get_redis()
        key = f"video_task:{task_id}"
        data = await redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def process_video(
        self,
        task_id: str,
        model_id: str,
        video_path: str,
        triton_model_name: str,
        class_names: Optional[List[str]],
        class_colors: Optional[Dict[str, str]],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        sample_fps: Optional[float] = None
    ) -> None:
        """
        Main video processing pipeline:
        1. Extract video info
        2. Extract frames
        3. Run inference on each frame
        4. Render output video with detections
        """
        work_dir = os.path.join(self.temp_dir, f"video_task_{task_id}")
        frames_dir = os.path.join(work_dir, "frames")
        rendered_dir = os.path.join(work_dir, "rendered")
        
        try:
            os.makedirs(work_dir, exist_ok=True)
            os.makedirs(frames_dir, exist_ok=True)
            os.makedirs(rendered_dir, exist_ok=True)
            
            # Step 1: Get video info
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "analyzing",
                "total_frames": 0,
                "processed_frames": 0,
                "progress_percent": 0,
            })
            
            video_info = await self.get_video_info(video_path)
            fps = video_info["fps"]
            total_frames = video_info["total_frames"]
            duration = video_info["duration"]
            
            # Check video duration limit
            if duration > MAX_VIDEO_DURATION:
                await self.update_task_status(task_id, VideoTaskStatus.FAILED, {
                    "model_id": model_id,
                    "error_message": f"视频时长超过限制：{duration:.1f}秒 (最大允许 {MAX_VIDEO_DURATION // 60} 分钟)",
                    "current_stage": "failed",
                })
                return
            
            # Step 2: Extract frames
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "decoding",
                "total_frames": total_frames,
                "processed_frames": 0,
                "progress_percent": 0,
                "fps": fps,
                "duration_seconds": duration,
            })
            
            extract_fps = sample_fps or fps
            frame_paths = await self.extract_frames(video_path, frames_dir, extract_fps)
            total_frames = len(frame_paths)
            
            # Step 3: Run inference on each frame
            frame_results = []
            
            for i, frame_path in enumerate(frame_paths):
                # Check if task was cancelled
                task_status = await self.get_task_status(task_id)
                if task_status and task_status.get("status") == "cancelled":
                    return  # Stop processing
                
                # Update progress
                progress = (i + 1) / total_frames * 80  # 0-80% for inference
                await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                    "model_id": model_id,
                    "current_stage": "inferring",
                    "total_frames": total_frames,
                    "processed_frames": i + 1,
                    "progress_percent": progress,
                    "fps": fps,
                    "duration_seconds": duration,
                })
                
                # Run inference
                result = await self.infer_frame(
                    frame_path=frame_path,
                    model_name=triton_model_name,
                    class_names=class_names,
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold
                )
                
                frame_results.append({
                    "frame_index": i,
                    "timestamp_ms": (i / fps) * 1000,
                    "boxes": result.get("boxes", []),
                    "scores": result.get("scores", []),
                    "labels": result.get("labels", []),
                    "class_names": result.get("class_names", []),
                })
                
                # Render frame with detections
                rendered_path = os.path.join(rendered_dir, f"rendered_{i+1:06d}.jpg")
                self.draw_detections_on_frame(
                    frame_path=frame_path,
                    output_path=rendered_path,
                    detection_result=result,
                    class_colors=class_colors
                )
            
            # Step 4: Render output video
            await self.update_task_status(task_id, VideoTaskStatus.RENDERING, {
                "model_id": model_id,
                "current_stage": "rendering",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 85,
                "fps": fps,
                "duration_seconds": duration,
            })
            
            output_video_path = os.path.join(work_dir, "output.mp4")
            await self.render_video(rendered_dir, output_video_path, fps)
            
            # Step 5: Upload results to MinIO
            await self.update_task_status(task_id, VideoTaskStatus.RENDERING, {
                "model_id": model_id,
                "current_stage": "uploading",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 95,
                "fps": fps,
                "duration_seconds": duration,
            })
            
            # Upload rendered video
            render_object_name = f"video_results/{task_id}/output.mp4"
            with open(output_video_path, "rb") as f:
                video_size = os.path.getsize(output_video_path)
                await upload_file(
                    bucket=settings.MINIO_BUCKET_TEMP,
                    object_name=render_object_name,
                    file_data=f,
                    file_size=video_size,
                    content_type="video/mp4"
                )
            
            # Upload JSON results
            result_data = {
                "task_id": task_id,
                "model_id": model_id,
                "total_frames": total_frames,
                "fps": fps,
                "duration_seconds": duration,
                "class_colors": class_colors,
                "video_info": video_info,
                "frame_results": frame_results,
            }
            
            result_object_name = f"video_results/{task_id}/result.json"
            result_bytes = json.dumps(result_data, ensure_ascii=False).encode("utf-8")
            await upload_file(
                bucket=settings.MINIO_BUCKET_TEMP,
                object_name=result_object_name,
                file_data=io.BytesIO(result_bytes),
                file_size=len(result_bytes),
                content_type="application/json"
            )
            
            # Mark as completed
            await self.update_task_status(task_id, VideoTaskStatus.COMPLETED, {
                "model_id": model_id,
                "current_stage": "completed",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 100,
                "fps": fps,
                "duration_seconds": duration,
                "render_path": render_object_name,
                "result_path": result_object_name,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            
        except Exception as e:
            await self.update_task_status(task_id, VideoTaskStatus.FAILED, {
                "model_id": model_id,
                "current_stage": "failed",
                "error_message": str(e),
            })
            raise
        finally:
            # Cleanup temp files
            import shutil
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)


# Singleton instance
video_inference_service = VideoInferenceService()
