"""HLS segment encoder for progressive video preview

Encodes rendered frames into MPEG-TS segments and generates HLS m3u8 manifests.
Segments are uploaded to MinIO as they are produced, enabling progressive playback
while inference is still running.
"""

import asyncio
import io
import logging
import os
import subprocess
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# GPU acceleration settings (shared with video_inference)
USE_GPU = os.getenv("USE_GPU", "true").lower() == "true"
GPU_DEVICE = os.getenv("GPU_DEVICE", "0")


def _check_nvenc_available() -> bool:
    """Check if NVENC encoder is available"""
    if not USE_GPU:
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


NVENC_AVAILABLE = _check_nvenc_available()


class HLSSegmentEncoder:
    """Encodes raw RGB frames into HLS .ts segments and generates .m3u8 manifests.

    Usage:
        encoder = HLSSegmentEncoder(task_id="abc", fps=30, width=1920, height=1080)
        ts_bytes = await encoder.encode_segment(frames, segment_index=0)
        manifest = encoder.generate_manifest(segment_count=1, is_final=False)
    """

    def __init__(
        self,
        task_id: str,
        fps: float,
        width: int,
        height: int,
        segment_duration: float = 4.0,
    ):
        self.task_id = task_id
        self.fps = fps
        self.width = width
        self.height = height
        self.segment_duration = segment_duration
        self.frames_per_segment = int(fps * segment_duration)
        self.segment_durations: List[float] = []

    async def encode_segment(
        self,
        frames: List[np.ndarray],
        segment_index: int,
    ) -> bytes:
        """Encode a list of raw RGB frames into a single MPEG-TS segment.

        Args:
            frames: List of numpy arrays with shape (H, W, 3), dtype uint8, RGB.
            segment_index: Zero-based segment index (for logging).

        Returns:
            Raw bytes of the .ts segment.
        """
        if not frames:
            return b""

        actual_duration = len(frames) / self.fps
        self.segment_durations.append(actual_duration)

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
        ]

        if NVENC_AVAILABLE:
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-tune", "ll",  # low-latency for streaming
                "-gpu", GPU_DEVICE,
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "fast",
                "-tune", "zerolatency",
            ])

        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-f", "mpegts",
            "-loglevel", "error",
            "pipe:1",
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        input_data = b"".join(frame.tobytes() for frame in frames)
        stdout, stderr = await proc.communicate(input=input_data)

        if proc.returncode != 0:
            # Fallback: retry with CPU encoder if NVENC failed
            if NVENC_AVAILABLE:
                logger.warning(
                    "[HLS] NVENC encode failed for segment %d, retrying with libx264: %s",
                    segment_index, stderr.decode(errors="replace"),
                )
                return await self._encode_segment_cpu(frames, segment_index)
            raise RuntimeError(
                f"HLS segment encode failed: {stderr.decode(errors='replace')}"
            )

        logger.debug(
            "[HLS] Encoded segment %d: %d frames, %.1fs, %d bytes",
            segment_index, len(frames), actual_duration, len(stdout),
        )
        return stdout

    async def _encode_segment_cpu(
        self,
        frames: List[np.ndarray],
        segment_index: int,
    ) -> bytes:
        """CPU fallback encoder for a single segment."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-f", "mpegts",
            "-loglevel", "error",
            "pipe:1",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        input_data = b"".join(frame.tobytes() for frame in frames)
        stdout, stderr = await proc.communicate(input=input_data)

        if proc.returncode != 0:
            raise RuntimeError(
                f"HLS CPU segment encode failed: {stderr.decode(errors='replace')}"
            )

        return stdout

    def generate_manifest(
        self,
        segment_count: int,
        is_final: bool = False,
    ) -> str:
        """Generate an HLS .m3u8 playlist manifest.

        Args:
            segment_count: Number of segments currently available.
            is_final: If True, adds EXT-X-ENDLIST to signal VOD completion.

        Returns:
            The m3u8 playlist as a string.
        """
        # Calculate max segment duration for TARGETDURATION
        if self.segment_durations:
            max_duration = max(self.segment_durations[:segment_count])
        else:
            max_duration = self.segment_duration
        target_duration = int(max_duration) + 1

        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{target_duration}",
            "#EXT-X-MEDIA-SEQUENCE:0",
        ]

        if is_final:
            lines.append("#EXT-X-PLAYLIST-TYPE:VOD")
        else:
            lines.append("#EXT-X-PLAYLIST-TYPE:EVENT")

        for i in range(segment_count):
            if i < len(self.segment_durations):
                duration = self.segment_durations[i]
            else:
                duration = self.segment_duration
            lines.append(f"#EXTINF:{duration:.3f},")
            lines.append(f"segment_{i:04d}.ts")

        if is_final:
            lines.append("#EXT-X-ENDLIST")

        return "\n".join(lines) + "\n"

    async def encode_original_video_hls(
        self,
        video_path: str,
        output_dir: str,
    ) -> int:
        """Transcode original video to HLS segments using FFmpeg.

        This runs FFmpeg directly with -hls_* options to produce .ts segments
        and a playlist.m3u8 on disk, which are then uploaded to MinIO.

        Args:
            video_path: Path to the original video file.
            output_dir: Directory to write HLS files to.

        Returns:
            Number of segments produced.
        """
        os.makedirs(output_dir, exist_ok=True)
        manifest_path = os.path.join(output_dir, "playlist.m3u8")
        segment_pattern = os.path.join(output_dir, "segment_%04d.ts")

        cmd = ["ffmpeg", "-y"]
        if NVENC_AVAILABLE:
            cmd.extend(["-hwaccel", "cuda", "-hwaccel_device", GPU_DEVICE])
        cmd.extend(["-i", video_path])

        if NVENC_AVAILABLE:
            cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "fast"])

        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-an",  # no audio for detection overlay playback
            "-f", "hls",
            "-hls_time", str(int(self.segment_duration)),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", segment_pattern,
            "-loglevel", "error",
            manifest_path,
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            if NVENC_AVAILABLE:
                logger.warning(
                    "[HLS] GPU transcode failed, retrying with CPU: %s",
                    stderr.decode(errors="replace"),
                )
                return await self._encode_original_video_hls_cpu(
                    video_path, output_dir
                )
            raise RuntimeError(
                f"HLS original video transcode failed: {stderr.decode(errors='replace')}"
            )

        # Count produced segments
        segment_count = len([
            f for f in os.listdir(output_dir)
            if f.startswith("segment_") and f.endswith(".ts")
        ])
        logger.info(
            "[HLS] Original video transcoded: %d segments", segment_count
        )
        return segment_count

    async def _encode_original_video_hls_cpu(
        self,
        video_path: str,
        output_dir: str,
    ) -> int:
        """CPU fallback for original video HLS transcode."""
        manifest_path = os.path.join(output_dir, "playlist.m3u8")
        segment_pattern = os.path.join(output_dir, "segment_%04d.ts")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            "-f", "hls",
            "-hls_time", str(int(self.segment_duration)),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", segment_pattern,
            "-loglevel", "error",
            manifest_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"HLS CPU transcode failed: {stderr.decode(errors='replace')}"
            )

        segment_count = len([
            f for f in os.listdir(output_dir)
            if f.startswith("segment_") and f.endswith(".ts")
        ])
        return segment_count
