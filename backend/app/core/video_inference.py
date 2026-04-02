"""Video inference service using FFmpeg for decoding and Triton for inference

Supports NVIDIA GPU hardware acceleration (NVENC/NVDEC) for faster video processing.
"""

import asyncio
import io
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.frame_renderer import FrameRenderer
from app.core.gpu_manager import GPUManager
from app.core.hls_encoder import HLSSegmentEncoder
from app.core.minio import upload_file
from app.core.model_adapter import (
    ModelAdapter,
    OwlModelAdapter,
    YOLOModelAdapter,
)
from app.core.redis import get_redis
from app.schemas.inference import VideoTaskStatus

logger = logging.getLogger(__name__)


# Maximum video size: 10GB
MAX_VIDEO_SIZE = 10 * 1024 * 1024 * 1024  # 10GB in bytes
# Maximum video duration: 180 minutes
MAX_VIDEO_DURATION = 180 * 60  # 10800 seconds

# GPU acceleration settings
USE_GPU = os.getenv("USE_GPU", "true").lower() == "true"
GPU_DEVICE = os.getenv("GPU_DEVICE", "0")  # GPU device index

# Concurrent inference window size for video processing
VIDEO_INFERENCE_CONCURRENCY = int(os.getenv("VIDEO_INFERENCE_CONCURRENCY", "4"))


def check_gpu_available() -> bool:
    """Check if NVIDIA GPU is available for hardware acceleration"""
    if not USE_GPU:
        return False

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f"[VideoInference] GPU detected: {result.stdout.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("[VideoInference] No GPU detected, using CPU mode")
    return False


# Check GPU availability at module load
GPU_AVAILABLE = check_gpu_available()


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
        """Extract frames from video using FFmpeg with GPU acceleration if available"""
        os.makedirs(output_dir, exist_ok=True)

        if GPU_AVAILABLE:
            # GPU-accelerated decoding using NVDEC
            # -hwaccel cuda: Use NVIDIA GPU for H.264/H.265 hardware decoding
            # Frames are auto-copied to system memory for CPU filter processing
            cmd = [
                "ffmpeg",
                "-hwaccel", "cuda",
                "-hwaccel_device", GPU_DEVICE,
                "-i", video_path,
            ]

            if fps:
                cmd.extend(["-vf", f"fps={fps}"])

            cmd.extend([
                "-q:v", "2",
                f"{output_dir}/frame_%06d.jpg"
            ])
        else:
            # CPU fallback
            cmd = [
                "ffmpeg",
                "-i", video_path,
            ]

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
            # If GPU failed, try CPU fallback
            if GPU_AVAILABLE:
                print(f"[VideoInference] GPU decoding failed, falling back to CPU: {stderr.decode()}")
                return await self._extract_frames_cpu(video_path, output_dir, fps)
            raise RuntimeError(f"FFmpeg frame extraction failed: {stderr.decode()}")

        # Get list of extracted frames
        frames = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ])

        return frames

    async def _extract_frames_cpu(
        self,
        video_path: str,
        output_dir: str,
        fps: Optional[float] = None
    ) -> List[str]:
        """CPU fallback for frame extraction"""
        cmd = [
            "ffmpeg",
            "-i", video_path,
        ]

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
            raise RuntimeError(f"FFmpeg CPU frame extraction failed: {stderr.decode()}")

        frames = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ])

        return frames


    # Shared renderer instance — font loaded once, reused across all frames
    _renderer: Optional[FrameRenderer] = None

    @classmethod
    def get_renderer(cls) -> FrameRenderer:
        if cls._renderer is None:
            cls._renderer = FrameRenderer()
        return cls._renderer

    def draw_detections_on_frame(
        self,
        frame_path: str,
        output_path: str,
        detection_result: Dict[str, Any],
        class_colors: Optional[Dict[str, str]],
        line_width: int = 2,
        font_size: int = 14,
    ) -> None:
        """Draw detection boxes on a frame and save.

        Kept for backward compatibility (used by ``export_video_with_classes``
        and ``process_export_video_task``).  Delegates to :class:`FrameRenderer`.
        """
        self.get_renderer().render_to_file(
            frame_path, output_path, detection_result, class_colors
        )

    async def render_video(
        self,
        frames_dir: str,
        output_path: str,
        fps: float
    ) -> None:
        """Render frames back to video using FFmpeg with GPU acceleration if available"""

        if GPU_AVAILABLE:
            # GPU-accelerated encoding using NVENC (h264_nvenc)
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate", str(fps),
                "-i", f"{frames_dir}/rendered_%06d.jpg",
                "-c:v", "h264_nvenc",  # NVIDIA GPU encoder
                "-preset", "p4",  # Performance preset (p1=fastest, p7=slowest)
                "-tune", "hq",  # High quality tuning
                "-rc", "vbr",  # Variable bitrate
                "-cq", "23",  # Constant quality (lower = better quality)
                "-b:v", "0",  # Let cq control quality
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ]
        else:
            # CPU fallback with libx264
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate", str(fps),
                "-i", f"{frames_dir}/rendered_%06d.jpg",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "23",
                "-movflags", "+faststart",
                output_path
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            # If GPU encoding failed, try CPU fallback
            if GPU_AVAILABLE:
                print(f"[VideoInference] GPU encoding failed, falling back to CPU: {stderr.decode()}")
                await self._render_video_cpu(frames_dir, output_path, fps)
                return
            raise RuntimeError(f"FFmpeg video render failed: {stderr.decode()}")

    async def _render_video_cpu(
        self,
        frames_dir: str,
        output_path: str,
        fps: float
    ) -> None:
        """CPU fallback for video rendering"""
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate", str(fps),
            "-i", f"{frames_dir}/rendered_%06d.jpg",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "23",
            "-movflags", "+faststart",
            output_path
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg CPU video render failed: {stderr.decode()}")

    async def _prepare_playback_video(
        self,
        video_path: str,
        output_path: str,
    ) -> None:
        """Re-encode original video to browser-compatible H.264 MP4 with faststart.

        Browsers only support limited codecs in <video> tag (H.264/VP9).
        The user's uploaded video may use unsupported codecs (H.265, etc.),
        so we re-encode to ensure playback works.
        """
        if GPU_AVAILABLE:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", "20",
                "-b:v", "0",
                "-pix_fmt", "yuv420p",
                "-an",  # No audio needed for detection overlay playback
                "-movflags", "+faststart",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "20",
                "-an",
                "-movflags", "+faststart",
                output_path,
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            if GPU_AVAILABLE:
                # GPU failed, try CPU fallback
                print(f"[VideoInference] GPU playback re-encode failed, falling back to CPU: {stderr.decode()}")
                cmd_cpu = [
                    "ffmpeg",
                    "-y",
                    "-i", video_path,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-crf", "20",
                    "-an",
                    "-movflags", "+faststart",
                    output_path,
                ]
                proc2 = await asyncio.create_subprocess_exec(
                    *cmd_cpu,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr2 = await proc2.communicate()
                if proc2.returncode != 0:
                    raise RuntimeError(f"FFmpeg playback re-encode failed: {stderr2.decode()}")
            else:
                raise RuntimeError(f"FFmpeg playback re-encode failed: {stderr.decode()}")

    async def export_video_with_classes(
        self,
        task_id: str,
        selected_classes: List[str],
        class_colors: Optional[Dict[str, str]] = None,
    ) -> str:
        """Export video with only selected class detections overlaid.

        Downloads original video and result JSON from MinIO,
        re-renders frames with only selected classes, and encodes to MP4.
        Returns path to the exported MP4 file.
        """
        from app.core.config import settings
        from app.core.minio import download_file, download_file_to_path

        # Get task data
        task_data = await self.get_task_status(task_id)
        if not task_data:
            raise RuntimeError(f"Task {task_id} not found")

        # Download original video from MinIO
        original_path = task_data.get("original_path")
        render_path = task_data.get("render_path")
        result_path = task_data.get("result_path")

        if not result_path:
            raise RuntimeError("Result JSON not found for this task")

        video_path_minio = original_path or render_path
        if not video_path_minio:
            raise RuntimeError("No video found for this task")

        # Create temp directory for export
        export_dir = tempfile.mkdtemp(prefix="video_export_")

        try:
            # Download result JSON (small, OK to load fully in memory)
            result_data = await download_file(settings.MINIO_BUCKET_TEMP, result_path)
            result_json = json.loads(result_data.decode())
            del result_data  # free JSON bytes immediately

            # Stream-download video directly to file (avoid loading GBs into RAM)
            video_file = os.path.join(export_dir, "input_video.mp4")
            await download_file_to_path(
                settings.MINIO_BUCKET_TEMP, video_path_minio, video_file
            )

            # Extract frames
            frames_dir = os.path.join(export_dir, "frames")
            fps = result_json.get("fps", 30)
            frames = await self.extract_frames(video_file, frames_dir, fps=fps)

            if not frames:
                raise RuntimeError("No frames extracted")

            # Render only selected class detections on frames
            frame_results = result_json.get("frame_results", [])
            rendered_dir = os.path.join(export_dir, "rendered")
            os.makedirs(rendered_dir, exist_ok=True)

            for i, frame_path in enumerate(frames):
                rendered_path = os.path.join(rendered_dir, f"rendered_{i+1:06d}.jpg")

                if i < len(frame_results):
                    frame_data = frame_results[i]
                    # Filter detection results by selected classes
                    filtered = self._filter_detections_by_class(frame_data, selected_classes)

                    if filtered["boxes"]:
                        self.draw_detections_on_frame(
                            frame_path, rendered_path, filtered, class_colors
                        )
                    else:
                        # No detections for selected classes, copy original
                        import shutil
                        shutil.copy2(frame_path, rendered_path)
                else:
                    import shutil
                    shutil.copy2(frame_path, rendered_path)

            # Encode to MP4
            output_path = os.path.join(export_dir, "export.mp4")
            await self.render_video(rendered_dir, output_path, fps)

            return output_path

        except Exception:
            # Clean up on error
            import shutil
            shutil.rmtree(export_dir, ignore_errors=True)
            raise

    def _filter_detections_by_class(
        self,
        frame_data: Dict[str, Any],
        selected_classes: List[str]
    ) -> Dict[str, Any]:
        """Filter detection results to keep only selected classes"""
        filtered_boxes = []
        filtered_scores = []
        filtered_class_names = []

        boxes = frame_data.get("boxes", [])
        scores = frame_data.get("scores", [])
        class_names = frame_data.get("class_names", [])

        for i, class_name in enumerate(class_names):
            if class_name in selected_classes:
                if i < len(boxes):
                    filtered_boxes.append(boxes[i])
                if i < len(scores):
                    filtered_scores.append(scores[i])
                filtered_class_names.append(class_name)

        return {
            "boxes": filtered_boxes,
            "scores": filtered_scores,
            "class_names": filtered_class_names,
        }

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

        await redis.set(key, json.dumps(task_data), ex=86400 * 30)  # 30 day TTL

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status from Redis"""
        redis = await get_redis()
        key = f"video_task:{task_id}"
        data = await redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def update_export_task_status(
        self,
        export_task_id: str,
        status: VideoTaskStatus,
        progress_data: Dict[str, Any]
    ) -> None:
        """Update export task status in Redis"""
        redis = await get_redis()
        key = f"video_export_task:{export_task_id}"

        task_data = {
            "export_task_id": export_task_id,
            "status": status.value,
            **progress_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await redis.set(key, json.dumps(task_data), ex=86400 * 30)  # 30 day TTL

    async def get_export_task_status(self, export_task_id: str) -> Optional[Dict[str, Any]]:
        """Get export task status from Redis"""
        redis = await get_redis()
        key = f"video_export_task:{export_task_id}"
        data = await redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def request_cancel_export_task(self, export_task_id: str) -> None:
        """Mark export task as cancelled"""
        current = await self.get_export_task_status(export_task_id)
        if not current:
            return

        await self.update_export_task_status(
            export_task_id,
            VideoTaskStatus.CANCELLED,
            {
                **current,
                "cancel_requested": True,
                "current_stage": "cancelled",
                "progress_percent": current.get("progress_percent", 0),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_ready": False,
            },
        )

    async def process_export_video_task(
        self,
        export_task_id: str,
        task_id: str,
        model_id: str,
        selected_classes: List[str],
        class_colors: Optional[Dict[str, str]] = None,
    ) -> None:
        """Process video export in background with progress reporting"""
        import shutil

        from app.core.config import settings
        from app.core.minio import download_file, download_file_to_path

        start_time = datetime.now(timezone.utc)

        def elapsed_seconds() -> float:
            return max(0.0, (datetime.now(timezone.utc) - start_time).total_seconds())

        async def push_status(
            status: VideoTaskStatus,
            current_stage: str,
            progress_percent: float,
            total_frames: int = 0,
            processed_frames: int = 0,
            eta_seconds: Optional[float] = None,
            output_ready: bool = False,
            error_message: Optional[str] = None,
            extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            payload = {
                "task_id": task_id,
                "model_id": model_id,
                "selected_classes": selected_classes,
                "current_stage": current_stage,
                "total_frames": total_frames,
                "processed_frames": processed_frames,
                "progress_percent": progress_percent,
                "elapsed_seconds": elapsed_seconds(),
                "eta_seconds": eta_seconds,
                "output_ready": output_ready,
                "error_message": error_message,
                "started_at": start_time.isoformat(),
            }
            if extra:
                payload.update(extra)
            if status in [VideoTaskStatus.COMPLETED, VideoTaskStatus.FAILED, VideoTaskStatus.CANCELLED]:
                payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            await self.update_export_task_status(export_task_id, status, payload)

        async def is_cancel_requested() -> bool:
            current = await self.get_export_task_status(export_task_id)
            if not current:
                return False
            return bool(current.get("cancel_requested") or current.get("status") == VideoTaskStatus.CANCELLED.value)

        export_dir = tempfile.mkdtemp(prefix=f"video_export_{export_task_id}_")

        try:
            await push_status(VideoTaskStatus.PROCESSING, "preparing", 0)

            task_data = await self.get_task_status(task_id)
            if not task_data:
                raise RuntimeError(f"Task {task_id} not found")

            original_path = task_data.get("original_path")
            render_path = task_data.get("render_path")
            result_path = task_data.get("result_path")

            if not result_path:
                raise RuntimeError("Result JSON not found for this task")

            video_path_minio = original_path or render_path
            if not video_path_minio:
                raise RuntimeError("No video found for this task")

            await push_status(VideoTaskStatus.PROCESSING, "downloading_assets", 8)

            result_data = await download_file(settings.MINIO_BUCKET_TEMP, result_path)
            result_json = json.loads(result_data.decode())
            del result_data

            if await is_cancel_requested():
                await push_status(VideoTaskStatus.CANCELLED, "cancelled", 8)
                return

            video_file = os.path.join(export_dir, "input_video.mp4")
            await download_file_to_path(settings.MINIO_BUCKET_TEMP, video_path_minio, video_file)

            if await is_cancel_requested():
                await push_status(VideoTaskStatus.CANCELLED, "cancelled", 12)
                return

            await push_status(VideoTaskStatus.PROCESSING, "decoding", 20)

            frames_dir = os.path.join(export_dir, "frames")
            fps = result_json.get("fps", 30)
            frames = await self.extract_frames(video_file, frames_dir, fps=fps)

            if not frames:
                raise RuntimeError("No frames extracted")

            frame_results = result_json.get("frame_results", [])
            rendered_dir = os.path.join(export_dir, "rendered")
            os.makedirs(rendered_dir, exist_ok=True)

            total_frames = len(frames)
            await push_status(VideoTaskStatus.PROCESSING, "filtering", 30, total_frames=total_frames, processed_frames=0)

            for i, frame_path in enumerate(frames):
                if await is_cancel_requested():
                    await push_status(
                        VideoTaskStatus.CANCELLED,
                        "cancelled",
                        30 + (i / max(1, total_frames)) * 55,
                        total_frames=total_frames,
                        processed_frames=i,
                    )
                    return

                rendered_path = os.path.join(rendered_dir, f"rendered_{i+1:06d}.jpg")

                if i < len(frame_results):
                    frame_data = frame_results[i]
                    filtered = self._filter_detections_by_class(frame_data, selected_classes)

                    if filtered["boxes"]:
                        self.draw_detections_on_frame(
                            frame_path, rendered_path, filtered, class_colors
                        )
                    else:
                        shutil.copy2(frame_path, rendered_path)
                else:
                    shutil.copy2(frame_path, rendered_path)

                processed = i + 1
                progress = 30 + (processed / max(1, total_frames)) * 55
                elapsed = elapsed_seconds()
                eta: Optional[float] = None
                if processed > 0 and total_frames > processed:
                    avg_per_frame = elapsed / processed
                    eta = avg_per_frame * (total_frames - processed)

                await push_status(
                    VideoTaskStatus.PROCESSING,
                    "filtering",
                    progress,
                    total_frames=total_frames,
                    processed_frames=processed,
                    eta_seconds=eta,
                )

            if await is_cancel_requested():
                await push_status(VideoTaskStatus.CANCELLED, "cancelled", 85, total_frames=total_frames, processed_frames=total_frames)
                return

            await push_status(VideoTaskStatus.RENDERING, "rendering", 90, total_frames=total_frames, processed_frames=total_frames)

            output_path = os.path.join(export_dir, "export.mp4")
            await self.render_video(rendered_dir, output_path, fps)

            if await is_cancel_requested():
                await push_status(VideoTaskStatus.CANCELLED, "cancelled", 92, total_frames=total_frames, processed_frames=total_frames)
                return

            await push_status(VideoTaskStatus.RENDERING, "uploading", 96, total_frames=total_frames, processed_frames=total_frames)

            export_object_name = f"video_results/{task_id}/exports/{export_task_id}.mp4"
            with open(output_path, "rb") as f:
                export_size = os.path.getsize(output_path)
                await upload_file(
                    bucket=settings.MINIO_BUCKET_TEMP,
                    object_name=export_object_name,
                    file_data=f,
                    file_size=export_size,
                    content_type="video/mp4",
                )

            await push_status(
                VideoTaskStatus.COMPLETED,
                "completed",
                100,
                total_frames=total_frames,
                processed_frames=total_frames,
                eta_seconds=0,
                output_ready=True,
                extra={
                    "export_path": export_object_name,
                    "output_size": export_size,
                },
            )

        except Exception as e:
            await push_status(
                VideoTaskStatus.FAILED,
                "failed",
                100,
                error_message=str(e),
                output_ready=False,
            )
            raise
        finally:
            if os.path.exists(export_dir):
                shutil.rmtree(export_dir, ignore_errors=True)

    # ================================================================== #
    #  Unified Video Inference Pipeline
    # ================================================================== #

    async def process_video_unified(
        self,
        task_id: str,
        model_id: str,
        video_path: str,
        adapter: ModelAdapter,
        class_colors: Optional[Dict[str, str]],
        conf_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
        sample_fps: Optional[float] = None,
    ) -> None:
        """Unified video processing pipeline for any model type.

        All models use the batch + HLS pipeline (decode → infer →
        progressive HLS encode) which provides real-time preview and
        per-frame Redis result publishing.  Non-batch models (e.g. OWL)
        run with ``batch_size=1``.
        """
        # Use adapter defaults when caller did not override
        if conf_threshold is None:
            conf_threshold = adapter.default_conf_threshold
        if iou_threshold is None:
            iou_threshold = adapter.default_iou_threshold

        renderer = self.get_renderer()

        await self._pipeline_batch_hls(
            task_id, model_id, video_path, adapter,
            class_colors, conf_threshold, iou_threshold,
            sample_fps, renderer,
        )

    # ------------------------------------------------------------------ #
    # Per-frame pipeline (DEPRECATED — kept for rollback safety)
    # All models now use _pipeline_batch_hls with batch_size=1 for
    # non-batch adapters.  This method is no longer called.
    # ------------------------------------------------------------------ #

    async def _pipeline_per_frame(
        self,
        task_id: str,
        model_id: str,
        video_path: str,
        adapter: ModelAdapter,
        class_colors: Optional[Dict[str, str]],
        conf_threshold: float,
        iou_threshold: float,
        sample_fps: Optional[float],
        renderer: FrameRenderer,
    ) -> None:
        work_dir = os.path.join(self.temp_dir, f"video_task_{task_id}")
        frames_dir = os.path.join(work_dir, "frames")
        rendered_dir = os.path.join(work_dir, "rendered")

        try:
            os.makedirs(work_dir, exist_ok=True)
            os.makedirs(frames_dir, exist_ok=True)
            os.makedirs(rendered_dir, exist_ok=True)

            start_time = datetime.now(timezone.utc)

            def _elapsed() -> float:
                return max(0.0, (datetime.now(timezone.utc) - start_time).total_seconds())

            # Step 1: Adapter preparation (e.g. OWL text encoding)
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "preparing",
                "total_frames": 0,
                "processed_frames": 0,
                "progress_percent": 0,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": 0,
            })
            await adapter.prepare()

            # Step 2: Get video info
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "analyzing",
                "total_frames": 0,
                "processed_frames": 0,
                "progress_percent": 2,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
            })

            video_info = await self.get_video_info(video_path)
            fps = video_info["fps"]
            total_frames = video_info["total_frames"]
            duration = video_info["duration"]

            if duration > MAX_VIDEO_DURATION:
                await self.update_task_status(task_id, VideoTaskStatus.FAILED, {
                    "model_id": model_id,
                    "error_message": f"视频时长超过限制：{duration:.1f}秒 (最大允许 {MAX_VIDEO_DURATION // 60} 分钟)",
                    "current_stage": "failed",
                })
                return

            # Step 3: Extract frames
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "decoding",
                "total_frames": total_frames,
                "processed_frames": 0,
                "progress_percent": 5,
                "fps": fps,
                "duration_seconds": duration,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
            })

            extract_fps = sample_fps or fps
            frame_paths = await self.extract_frames(video_path, frames_dir, extract_fps)
            total_frames = len(frame_paths)

            # Step 4: Concurrent inference + rendering
            frame_results: List[Optional[Dict]] = [None] * total_frames
            semaphore = asyncio.Semaphore(VIDEO_INFERENCE_CONCURRENCY)
            completed_count = 0

            async def _infer_and_render(i: int, fpath: str):
                nonlocal completed_count
                async with semaphore:
                    task_status = await self.get_task_status(task_id)
                    if task_status and task_status.get("status") == "cancelled":
                        return

                    with open(fpath, "rb") as f:
                        image_bytes = f.read()
                    try:
                        result = await asyncio.to_thread(
                            adapter.infer_frame_sync,
                            image_bytes, conf_threshold, iou_threshold,
                        )
                    finally:
                        del image_bytes

                    frame_results[i] = {
                        "frame_index": i,
                        "timestamp_ms": (i / fps) * 1000,
                        "boxes": result.get("boxes", []),
                        "scores": result.get("scores", []),
                        "labels": result.get("labels", []),
                        "class_names": result.get("class_names", []),
                    }

                    rendered_path = os.path.join(rendered_dir, f"rendered_{i+1:06d}.jpg")
                    await asyncio.to_thread(
                        renderer.render_to_file,
                        fpath, rendered_path, result, class_colors, adapter.render_mode,
                    )

                    completed_count += 1

            batch_size = VIDEO_INFERENCE_CONCURRENCY
            for batch_start in range(0, total_frames, batch_size):
                batch_end = min(batch_start + batch_size, total_frames)
                tasks = [
                    _infer_and_render(i, frame_paths[i])
                    for i in range(batch_start, batch_end)
                ]
                await asyncio.gather(*tasks)

                task_status = await self.get_task_status(task_id)
                if task_status and task_status.get("status") == "cancelled":
                    return

                progress = 5 + completed_count / max(1, total_frames) * 75
                elapsed = _elapsed()
                eta = None
                if completed_count >= 3 and completed_count < total_frames:
                    eta = (elapsed / completed_count) * (total_frames - completed_count)
                await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                    "model_id": model_id,
                    "current_stage": "inferring",
                    "total_frames": total_frames,
                    "processed_frames": completed_count,
                    "progress_percent": progress,
                    "fps": fps,
                    "duration_seconds": duration,
                    "started_at": start_time.isoformat(),
                    "elapsed_seconds": elapsed,
                    "eta_seconds": eta,
                })

            valid_results = [r for r in frame_results if r is not None]

            # Step 5: Render output video
            await self.update_task_status(task_id, VideoTaskStatus.RENDERING, {
                "model_id": model_id,
                "current_stage": "rendering",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 85,
                "fps": fps,
                "duration_seconds": duration,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
                "eta_seconds": None,
            })

            output_video_path = os.path.join(work_dir, "output.mp4")
            await self.render_video(rendered_dir, output_video_path, fps)

            # Step 6: Upload
            await self.update_task_status(task_id, VideoTaskStatus.RENDERING, {
                "model_id": model_id,
                "current_stage": "uploading",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 95,
                "fps": fps,
                "duration_seconds": duration,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
                "eta_seconds": None,
            })

            render_object_name = f"video_results/{task_id}/output.mp4"
            with open(output_video_path, "rb") as f:
                video_size = os.path.getsize(output_video_path)
                await upload_file(
                    bucket=settings.MINIO_BUCKET_TEMP,
                    object_name=render_object_name,
                    file_data=f,
                    file_size=video_size,
                    content_type="video/mp4",
                )

            playback_video_path = os.path.join(work_dir, "playback.mp4")
            await self._prepare_playback_video(video_path, playback_video_path)
            original_object_name = f"video_results/{task_id}/original.mp4"
            with open(playback_video_path, "rb") as f:
                original_size = os.path.getsize(playback_video_path)
                await upload_file(
                    bucket=settings.MINIO_BUCKET_TEMP,
                    object_name=original_object_name,
                    file_data=f,
                    file_size=original_size,
                    content_type="video/mp4",
                )

            result_data = {
                "task_id": task_id,
                "model_id": model_id,
                "total_frames": total_frames,
                "fps": fps,
                "duration_seconds": duration,
                "class_colors": class_colors,
                "video_info": video_info,
                "frame_results": valid_results,
                **adapter.extra_result_metadata(),
            }

            result_object_name = f"video_results/{task_id}/result.json"
            result_bytes = json.dumps(result_data, ensure_ascii=False).encode("utf-8")
            await upload_file(
                bucket=settings.MINIO_BUCKET_TEMP,
                object_name=result_object_name,
                file_data=io.BytesIO(result_bytes),
                file_size=len(result_bytes),
                content_type="application/json",
            )

            await self.update_task_status(task_id, VideoTaskStatus.COMPLETED, {
                "model_id": model_id,
                "current_stage": "completed",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 100,
                "fps": fps,
                "duration_seconds": duration,
                "render_path": render_object_name,
                "original_path": original_object_name,
                "result_path": result_object_name,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
                "eta_seconds": None,
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
            import shutil
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
            if os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    # Batch + HLS pipeline (used when adapter.supports_batch is True)
    # ------------------------------------------------------------------ #

    async def _pipeline_batch_hls(
        self,
        task_id: str,
        model_id: str,
        video_path: str,
        adapter: ModelAdapter,
        class_colors: Optional[Dict[str, str]],
        conf_threshold: float,
        iou_threshold: float,
        sample_fps: Optional[float],
        renderer: FrameRenderer,
    ) -> None:
        try:
            start_time = datetime.now(timezone.utc)

            def _elapsed() -> float:
                return max(0.0, (datetime.now(timezone.utc) - start_time).total_seconds())

            # Step 1: Adapter preparation
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "preparing",
                "total_frames": 0,
                "processed_frames": 0,
                "progress_percent": 0,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": 0,
            })
            await adapter.prepare()

            # Step 2: Analyze video
            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "analyzing",
                "total_frames": 0,
                "processed_frames": 0,
                "progress_percent": 1,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
            })

            video_info = await self.get_video_info(video_path)
            fps = video_info["fps"]
            width = video_info["width"]
            height = video_info["height"]
            duration = video_info["duration"]
            total_frames = video_info["total_frames"]

            if duration > MAX_VIDEO_DURATION:
                await self.update_task_status(task_id, VideoTaskStatus.FAILED, {
                    "model_id": model_id,
                    "error_message": (
                        f"视频时长超过限制：{duration:.1f}秒 "
                        f"(最大允许 {MAX_VIDEO_DURATION // 60} 分钟)"
                    ),
                    "current_stage": "failed",
                })
                return

            effective_fps = sample_fps or fps
            if sample_fps:
                total_frames = int(duration * sample_fps)

            if adapter.supports_batch:
                batch_size = self._determine_batch_size(width, height)
            else:
                batch_size = 1

            encoder = HLSSegmentEncoder(
                task_id=task_id,
                fps=effective_fps,
                width=width,
                height=height,
            )

            frame_queue: asyncio.Queue = asyncio.Queue(maxsize=batch_size * 2)
            result_queue: asyncio.Queue = asyncio.Queue(
                maxsize=encoder.frames_per_segment * 2,
            )

            await self.update_task_status(task_id, VideoTaskStatus.PROCESSING, {
                "model_id": model_id,
                "current_stage": "decoding",
                "total_frames": total_frames,
                "processed_frames": 0,
                "progress_percent": 2,
                "fps": effective_fps,
                "duration_seconds": duration,
                "batch_size": batch_size,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
            })

            # Launch three stages concurrently
            decode_task = asyncio.create_task(
                self._decode_frames_to_queue(
                    video_path, frame_queue, width, height, fps, sample_fps,
                )
            )
            infer_task = asyncio.create_task(
                self._batch_infer_stage(
                    frame_queue, result_queue, task_id, model_id,
                    adapter, class_colors,
                    conf_threshold, iou_threshold, batch_size,
                    effective_fps, total_frames, start_time, renderer,
                )
            )
            hls_task = asyncio.create_task(
                self._hls_encode_stage(result_queue, task_id, encoder)
            )

            actual_frame_count, frame_results, hls_result = await asyncio.gather(
                decode_task, infer_task, hls_task,
            )
            segment_count, total_hls_bytes = hls_result
            total_frames = actual_frame_count

            # Upload JSON results
            await self.update_task_status(task_id, VideoTaskStatus.RENDERING, {
                "model_id": model_id,
                "current_stage": "uploading",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 95,
                "fps": effective_fps,
                "duration_seconds": duration,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
            })

            protocol = "https" if settings.MINIO_SECURE else "http"
            hls_base_url = (
                f"{protocol}://{settings.MINIO_PUBLIC_ENDPOINT}"
                f"/{settings.MINIO_BUCKET_HLS}/{task_id}"
            )
            hls_playlist_url = f"{hls_base_url}/playlist.m3u8"

            # Transcode original video to HLS for side-by-side playback
            # (must happen BEFORE result.json so original_hls_url is included)
            original_hls_url = None
            original_hls_dir = os.path.join(
                self.temp_dir, f"hls_original_{task_id}",
            )
            try:
                original_encoder = HLSSegmentEncoder(
                    task_id=f"{task_id}_original",
                    fps=effective_fps,
                    width=width,
                    height=height,
                )
                await original_encoder.encode_original_video_hls(
                    video_path, original_hls_dir,
                )

                for fname in sorted(os.listdir(original_hls_dir)):
                    fpath = os.path.join(original_hls_dir, fname)
                    with open(fpath, "rb") as f:
                        fsize = os.path.getsize(fpath)
                        ct = (
                            "video/mp2t"
                            if fname.endswith(".ts")
                            else "application/vnd.apple.mpegurl"
                        )
                        await upload_file(
                            bucket=settings.MINIO_BUCKET_HLS,
                            object_name=f"{task_id}_original/{fname}",
                            file_data=f,
                            file_size=fsize,
                            content_type=ct,
                        )

                original_hls_url = (
                    f"{protocol}://{settings.MINIO_PUBLIC_ENDPOINT}"
                    f"/{settings.MINIO_BUCKET_HLS}"
                    f"/{task_id}_original/playlist.m3u8"
                )
            except Exception as e:
                logger.warning("[Pipeline] Original HLS transcode failed: %s", e)
            finally:
                import shutil
                if os.path.exists(original_hls_dir):
                    shutil.rmtree(original_hls_dir, ignore_errors=True)

            result_data = {
                "task_id": task_id,
                "model_id": model_id,
                "total_frames": total_frames,
                "fps": effective_fps,
                "duration_seconds": duration,
                "class_colors": class_colors,
                "video_info": video_info,
                "frame_results": frame_results,
                "hls_url": hls_playlist_url,
                "original_hls_url": original_hls_url,
                "hls_segments": segment_count,
                **adapter.extra_result_metadata(),
            }

            result_object_name = f"video_results/{task_id}/result.json"
            result_bytes = json.dumps(
                result_data, ensure_ascii=False,
            ).encode("utf-8")
            await upload_file(
                bucket=settings.MINIO_BUCKET_TEMP,
                object_name=result_object_name,
                file_data=io.BytesIO(result_bytes),
                file_size=len(result_bytes),
                content_type="application/json",
            )

            await self.update_task_status(task_id, VideoTaskStatus.COMPLETED, {
                "model_id": model_id,
                "current_stage": "completed",
                "total_frames": total_frames,
                "processed_frames": total_frames,
                "progress_percent": 100,
                "fps": effective_fps,
                "duration_seconds": duration,
                "result_path": result_object_name,
                "hls_url": hls_playlist_url,
                "original_hls_url": original_hls_url,
                "hls_segments": segment_count,
                "render_video_size": total_hls_bytes,
                "batch_size": batch_size,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": _elapsed(),
                "eta_seconds": None,
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
            if os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except OSError:
                    pass

    # ================================================================== #
    #  Backward-compatible delegation wrappers
    # ================================================================== #

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
        sample_fps: Optional[float] = None,
    ) -> None:
        """Legacy YOLO pipeline — delegates to :meth:`process_video_unified`."""
        adapter = YOLOModelAdapter(triton_model_name, class_names)
        await self.process_video_unified(
            task_id, model_id, video_path, adapter,
            class_colors, conf_threshold, iou_threshold, sample_fps,
        )

    async def process_video_owl(
        self,
        task_id: str,
        model_id: str,
        video_path: str,
        text_prompts: List[str],
        owl_variant: str = "owlv2-base-patch16",
        class_colors: Optional[Dict[str, str]] = None,
        conf_threshold: float = 0.1,
        iou_threshold: float = 0.3,
        sample_fps: Optional[float] = None,
    ) -> None:
        """Legacy OWL pipeline — delegates to :meth:`process_video_unified`."""
        adapter = OwlModelAdapter(text_prompts, owl_variant)
        await self.process_video_unified(
            task_id, model_id, video_path, adapter,
            class_colors, conf_threshold, iou_threshold, sample_fps,
        )

    async def process_video_pipeline(
        self,
        task_id: str,
        model_id: str,
        video_path: str,
        triton_model_name: str,
        class_names: Optional[List[str]],
        class_colors: Optional[Dict[str, str]],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        sample_fps: Optional[float] = None,
    ) -> None:
        """Legacy batch+HLS pipeline — delegates to :meth:`process_video_unified`."""
        adapter = YOLOModelAdapter(triton_model_name, class_names)
        await self.process_video_unified(
            task_id, model_id, video_path, adapter,
            class_colors, conf_threshold, iou_threshold, sample_fps,
        )

    # ================================================================== #
    #  Pipeline infrastructure (shared by batch+HLS path)
    # ================================================================== #

    def _determine_batch_size(
        self,
        width: int,
        height: int,
        default: int = 8,
        min_batch: int = 1,
        max_batch: int = 32,
    ) -> int:
        """Determine optimal batch size based on available GPU memory."""
        try:
            gpu_mgr = GPUManager()
            gpus = gpu_mgr.get_all_gpus_info()
            if not gpus:
                return default

            best_gpu = max(gpus, key=lambda g: g.memory_free)
            free_mb = best_gpu.memory_free / (1024 * 1024)

            available_mb = max(0, free_mb - 2048)
            estimated_per_frame_mb = 50
            batch_size = int(available_mb / estimated_per_frame_mb)

            batch_size = max(min_batch, min(batch_size, max_batch))
            logger.info(
                "[Pipeline] Auto batch size: %d (GPU %s, %.0f MB free)",
                batch_size, best_gpu.name, free_mb,
            )
            return batch_size
        except Exception as e:
            logger.warning(
                "[Pipeline] Failed to determine batch size: %s, using default %d",
                e, default,
            )
            return default

    # --- Stage 1: Streaming decode ---

    async def _decode_frames_to_queue(
        self,
        video_path: str,
        frame_queue: "asyncio.Queue[Optional[Tuple[int, np.ndarray]]]",
        width: int,
        height: int,
        fps: float,
        sample_fps: Optional[float] = None,
    ) -> int:
        """Decode video via FFmpeg pipe and push (index, rgb_array) into *frame_queue*."""
        cmd = ["ffmpeg"]
        if GPU_AVAILABLE:
            cmd.extend(["-hwaccel", "cuda", "-hwaccel_device", GPU_DEVICE])
        cmd.extend(["-i", video_path])

        if sample_fps:
            cmd.extend(["-vf", f"fps={sample_fps}"])

        cmd.extend([
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-loglevel", "error",
            "pipe:1",
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        frame_size = width * height * 3
        frame_index = 0

        try:
            while True:
                data = await proc.stdout.readexactly(frame_size)
                frame = np.frombuffer(data, dtype=np.uint8).reshape(
                    (height, width, 3)
                )
                await frame_queue.put((frame_index, frame.copy()))
                frame_index += 1
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error("[Pipeline] Decode error at frame %d: %s", frame_index, e)

        await proc.wait()

        if proc.returncode != 0 and frame_index == 0:
            stderr_data = await proc.stderr.read()
            if GPU_AVAILABLE:
                logger.warning(
                    "[Pipeline] GPU decode failed, retrying CPU: %s",
                    stderr_data.decode(errors="replace"),
                )
                return await self._decode_frames_to_queue_cpu(
                    video_path, frame_queue, width, height, fps, sample_fps,
                )
            raise RuntimeError(
                f"FFmpeg pipe decode failed: {stderr_data.decode(errors='replace')}"
            )

        await frame_queue.put(None)
        logger.info("[Pipeline] Decoded %d frames", frame_index)
        return frame_index

    async def _decode_frames_to_queue_cpu(
        self,
        video_path: str,
        frame_queue: "asyncio.Queue[Optional[Tuple[int, np.ndarray]]]",
        width: int,
        height: int,
        fps: float,
        sample_fps: Optional[float] = None,
    ) -> int:
        """CPU fallback for pipe-based frame decoding."""
        cmd = ["ffmpeg", "-i", video_path]

        if sample_fps:
            cmd.extend(["-vf", f"fps={sample_fps}"])

        cmd.extend([
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-loglevel", "error",
            "pipe:1",
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        frame_size = width * height * 3
        frame_index = 0

        try:
            while True:
                data = await proc.stdout.readexactly(frame_size)
                frame = np.frombuffer(data, dtype=np.uint8).reshape(
                    (height, width, 3)
                )
                await frame_queue.put((frame_index, frame.copy()))
                frame_index += 1
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error("[Pipeline] CPU decode error at frame %d: %s", frame_index, e)

        await proc.wait()

        if proc.returncode != 0 and frame_index == 0:
            stderr_data = await proc.stderr.read()
            raise RuntimeError(
                f"FFmpeg CPU pipe decode failed: {stderr_data.decode(errors='replace')}"
            )

        await frame_queue.put(None)
        logger.info("[Pipeline] CPU decoded %d frames", frame_index)
        return frame_index

    # --- Stage 2: Batch inference (adapter-based) ---

    async def _batch_infer_stage(
        self,
        frame_queue: "asyncio.Queue[Optional[Tuple[int, np.ndarray]]]",
        result_queue: "asyncio.Queue[Optional[Tuple[int, np.ndarray, Dict]]]",
        task_id: str,
        model_id: str,
        adapter: ModelAdapter,
        class_colors: Optional[Dict[str, str]],
        conf_threshold: float,
        iou_threshold: float,
        batch_size: int,
        fps: float,
        total_frames_hint: int,
        start_time: datetime,
        renderer: FrameRenderer,
    ) -> List[Dict[str, Any]]:
        """Read frames, run batched inference via adapter, draw detections,
        push rendered frames into *result_queue*."""
        all_results: List[Dict[str, Any]] = []
        batch_frames: List[Tuple[int, np.ndarray]] = []
        completed = 0
        redis = await get_redis()

        async def _process_batch(
            frames_batch: List[Tuple[int, np.ndarray]],
        ) -> None:
            nonlocal completed
            if not frames_batch:
                return

            images_bytes: List[bytes] = []
            for _, frame_arr in frames_batch:
                buf = io.BytesIO()
                Image.fromarray(frame_arr, "RGB").save(
                    buf, format="JPEG", quality=95,
                )
                images_bytes.append(buf.getvalue())

            batch_results = await adapter.infer_batch(
                images_bytes, conf_threshold, iou_threshold,
            )

            for (fidx, frame_arr), det_result in zip(frames_batch, batch_results):
                frame_det: Dict[str, Any] = {
                    "frame_index": fidx,
                    "timestamp_ms": (fidx / fps) * 1000,
                    "boxes": det_result.get("boxes", []),
                    "scores": det_result.get("scores", []),
                    "labels": det_result.get("labels", []),
                    "class_names": det_result.get("class_names", []),
                }
                all_results.append(frame_det)

                rendered = renderer.render(
                    frame_arr, det_result, class_colors, adapter.render_mode,
                )
                await result_queue.put((fidx, rendered, frame_det))

                try:
                    await redis.publish(
                        f"video_task:{task_id}:frames",
                        json.dumps(frame_det, ensure_ascii=False),
                    )
                except Exception:
                    pass

                completed += 1

            elapsed = max(
                0.0,
                (datetime.now(timezone.utc) - start_time).total_seconds(),
            )
            progress = completed / max(1, total_frames_hint) * 80
            eta = None
            if completed >= 3 and completed < total_frames_hint:
                eta = (elapsed / completed) * (total_frames_hint - completed)

            await self.update_task_status(
                task_id,
                VideoTaskStatus.PROCESSING,
                {
                    "model_id": model_id,
                    "current_stage": "inferring",
                    "total_frames": total_frames_hint,
                    "processed_frames": completed,
                    "progress_percent": progress,
                    "fps": fps,
                    "started_at": start_time.isoformat(),
                    "elapsed_seconds": elapsed,
                    "eta_seconds": eta,
                },
            )

        while True:
            item = await frame_queue.get()
            if item is None:
                if batch_frames:
                    await _process_batch(batch_frames)
                    batch_frames = []
                break

            batch_frames.append(item)
            if len(batch_frames) >= batch_size:
                await _process_batch(batch_frames)
                batch_frames = []

                task_status = await self.get_task_status(task_id)
                if task_status and task_status.get("status") == "cancelled":
                    break

        await result_queue.put(None)
        logger.info("[Pipeline] Inference complete: %d frames", completed)

        all_results.sort(key=lambda r: r["frame_index"])
        return all_results

    # --- Stage 3: HLS encoding & upload ---

    async def _hls_encode_stage(
        self,
        result_queue: "asyncio.Queue[Optional[Tuple[int, np.ndarray, Dict]]]",
        task_id: str,
        encoder: HLSSegmentEncoder,
    ) -> Tuple[int, int]:
        """Encode HLS segments from rendered frames and upload to MinIO."""
        segment_frames: List[np.ndarray] = []
        segment_index = 0
        total_bytes = 0
        redis = await get_redis()

        while True:
            item = await result_queue.get()
            if item is None:
                if segment_frames:
                    seg_size = await self._upload_hls_segment(
                        encoder, segment_frames, segment_index, task_id, redis,
                    )
                    total_bytes += seg_size
                    segment_index += 1
                break

            _, rendered_arr, _ = item
            segment_frames.append(rendered_arr)

            if len(segment_frames) >= encoder.frames_per_segment:
                seg_size = await self._upload_hls_segment(
                    encoder, segment_frames, segment_index, task_id, redis,
                )
                total_bytes += seg_size
                segment_index += 1
                segment_frames = []

        manifest = encoder.generate_manifest(segment_index, is_final=True)
        manifest_bytes = manifest.encode("utf-8")
        await upload_file(
            bucket=settings.MINIO_BUCKET_HLS,
            object_name=f"{task_id}/playlist.m3u8",
            file_data=io.BytesIO(manifest_bytes),
            file_size=len(manifest_bytes),
            content_type="application/vnd.apple.mpegurl",
        )
        total_bytes += len(manifest_bytes)

        try:
            await redis.publish(
                f"video_task:{task_id}:hls",
                json.dumps({"type": "manifest_final", "segments": segment_index}),
            )
        except Exception:
            pass

        logger.info("[Pipeline] HLS encode complete: %d segments, %d bytes", segment_index, total_bytes)
        return segment_index, total_bytes

    async def _upload_hls_segment(
        self,
        encoder: HLSSegmentEncoder,
        frames: List[np.ndarray],
        segment_index: int,
        task_id: str,
        redis,
    ) -> int:
        """Encode frames to .ts, upload segment + progressive manifest."""
        ts_bytes = await encoder.encode_segment(frames, segment_index)

        segment_name = f"segment_{segment_index:04d}.ts"
        await upload_file(
            bucket=settings.MINIO_BUCKET_HLS,
            object_name=f"{task_id}/{segment_name}",
            file_data=io.BytesIO(ts_bytes),
            file_size=len(ts_bytes),
            content_type="video/mp2t",
        )

        manifest = encoder.generate_manifest(segment_index + 1, is_final=False)
        manifest_bytes = manifest.encode("utf-8")
        await upload_file(
            bucket=settings.MINIO_BUCKET_HLS,
            object_name=f"{task_id}/playlist.m3u8",
            file_data=io.BytesIO(manifest_bytes),
            file_size=len(manifest_bytes),
            content_type="application/vnd.apple.mpegurl",
        )

        try:
            await redis.publish(
                f"video_task:{task_id}:hls",
                json.dumps({
                    "type": "segment",
                    "index": segment_index,
                    "name": segment_name,
                }),
            )
        except Exception:
            pass

        logger.debug(
            "[Pipeline] Uploaded segment %d (%d bytes)", segment_index, len(ts_bytes),
        )
        return len(ts_bytes)


# Singleton instance
video_inference_service = VideoInferenceService()
