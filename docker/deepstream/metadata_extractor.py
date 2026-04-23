"""Detection metadata extractor for DeepStream pipelines.

This module provides BatchMetadataOperator subclasses that extract
detection statistics from DeepStream's inference output and publish
them to Redis for the WebSocket layer to consume.

Classes:
    DetectionStatsExtractor - For real-time streaming: publishes aggregate
        stats (class counts) at ~10/s.
    FileDetectionExtractor - For video file inference: publishes per-frame
        bounding boxes without rate limiting, tracks progress, and
        accumulates all results for final JSON serialization on EOS.
"""

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List

import redis
from pyservicemaker import BatchMetadataOperator

logger = logging.getLogger(__name__)


class DetectionStatsExtractor(BatchMetadataOperator):
    """Extract detection statistics from nvinferserver output and publish to Redis.

    This operator is attached as a Probe to the pipeline after the inference
    element. It iterates over detected objects in each frame, counts them by
    class, and publishes a JSON stats payload to Redis PubSub for the backend
    WebSocket to forward to the frontend.
    """

    def __init__(
        self,
        session_id: str,
        class_names: List[str],
        class_colors: Dict[str, str],
        redis_client: redis.Redis,
    ):
        super().__init__()
        self.session_id = session_id
        self._labels = class_names
        self._class_colors = class_colors
        self._redis = redis_client
        self.frames_processed = 0
        self._latency_window: Deque[float] = deque(maxlen=100)
        self._last_publish_time = 0.0

    def handle_metadata(self, batch_meta: Any) -> None:
        """Called per batch by the DeepStream pipeline thread."""
        for frame_meta in batch_meta.frame_items:
            start = time.time()
            detection_count = 0
            class_counts: Dict[str, int] = {}

            for obj in frame_meta.object_items:
                detection_count += 1
                class_id = obj.class_id
                name = (
                    self._labels[class_id]
                    if class_id < len(self._labels)
                    else f"class_{class_id}"
                )
                class_counts[name] = class_counts.get(name, 0) + 1

            latency_ms = (time.time() - start) * 1000
            self.frames_processed += 1
            self._latency_window.append(latency_ms)

            # Rate-limit Redis publishes to ~10/s
            now = time.time()
            if now - self._last_publish_time < 0.1:
                continue
            self._last_publish_time = now

            result = {
                "type": "inference_result",
                "session_id": self.session_id,
                "frame_id": str(frame_meta.frame_number),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": latency_ms,
                "avg_latency_ms": (
                    sum(self._latency_window) / len(self._latency_window)
                    if self._latency_window
                    else 0
                ),
                "frames_processed": self.frames_processed,
                "detection_count": detection_count,
                "class_counts": class_counts,
                "class_colors": self._class_colors,
            }

            try:
                payload = json.dumps(result)
                channel = f"stream_results:{self.session_id}"
                self._redis.publish(channel, payload)
                self._redis.setex(
                    f"stream_result:{self.session_id}:latest", 3600, payload
                )
            except Exception as e:
                logger.error(f"Redis publish error for {self.session_id}: {e}")


class FileDetectionExtractor(BatchMetadataOperator):
    """Extract per-frame bounding boxes for video file inference.

    Unlike DetectionStatsExtractor which publishes aggregate stats at ~10/s,
    this extractor publishes every frame's full detection results (boxes,
    scores, labels) to Redis and accumulates them in memory for final JSON
    serialization when the pipeline reaches EOS.
    """

    def __init__(
        self,
        task_id: str,
        total_frames: int,
        fps: float,
        duration: float,
        class_names: List[str],
        class_colors: Dict[str, str],
        redis_client: redis.Redis,
    ):
        super().__init__()
        self.task_id = task_id
        self.total_frames = total_frames
        self.fps = fps
        self.duration = duration
        self._labels = class_names
        self._class_colors = class_colors
        self._redis = redis_client
        self.frames_processed = 0
        self._all_frame_results: List[dict] = []
        self._last_progress_time = 0.0
        self._start_time = time.time()

    def handle_metadata(self, batch_meta: Any) -> None:
        """Called per batch by DeepStream pipeline thread.

        Extracts full bounding box data from each frame and publishes to
        Redis without rate limiting. Also updates progress periodically.
        """
        for frame_meta in batch_meta.frame_items:
            self.frames_processed += 1
            boxes: List[List[float]] = []
            scores: List[float] = []
            labels: List[int] = []
            class_names_list: List[str] = []

            for obj in frame_meta.object_items:
                r = obj.rect_params
                boxes.append([
                    round(r.left, 2),
                    round(r.top, 2),
                    round(r.left + r.width, 2),
                    round(r.top + r.height, 2),
                ])
                scores.append(round(obj.confidence, 4))
                labels.append(obj.class_id)
                name = (
                    self._labels[obj.class_id]
                    if obj.class_id < len(self._labels)
                    else f"class_{obj.class_id}"
                )
                class_names_list.append(name)

            frame_result = {
                "frame_index": self.frames_processed - 1,
                "timestamp_ms": round(
                    ((self.frames_processed - 1) / self.fps) * 1000, 2
                ),
                "boxes": boxes,
                "scores": scores,
                "labels": labels,
                "class_names": class_names_list,
            }
            self._all_frame_results.append(frame_result)

            # Publish every frame result to Redis (no rate limiting)
            try:
                self._redis.publish(
                    f"video_task:{self.task_id}:frames",
                    json.dumps(frame_result),
                )
            except Exception:
                pass

            # Update progress every 200ms
            now = time.time()
            if now - self._last_progress_time >= 0.2:
                self._last_progress_time = now
                elapsed = now - self._start_time
                # Inference accounts for 80% of total progress
                progress = min(
                    80,
                    int(self.frames_processed / max(self.total_frames, 1) * 80),
                )
                eta = (
                    (elapsed / self.frames_processed)
                    * (self.total_frames - self.frames_processed)
                    if self.frames_processed > 0
                    else 0
                )
                try:
                    self._redis.setex(
                        f"video_task:{self.task_id}:progress",
                        3600,
                        json.dumps({
                            "processed_frames": self.frames_processed,
                            "total_frames": self.total_frames,
                            "progress_percent": progress,
                            "elapsed_seconds": round(elapsed, 1),
                            "eta_seconds": round(eta, 1),
                        }),
                    )
                except Exception:
                    pass

    def finalize(self) -> str:
        """Serialize accumulated results to JSON file on shared volume.

        Called when the pipeline reaches EOS.

        Returns:
            Path to the written JSON file.
        """
        result_dir = f"/shared/results/{self.task_id}"
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, "result_frames.json")
        with open(result_path, "w") as f:
            json.dump(self._all_frame_results, f)
        logger.info(
            f"FileDetectionExtractor finalized for {self.task_id}: "
            f"{self.frames_processed} frames, {len(self._all_frame_results)} results "
            f"written to {result_path}"
        )
        return result_path
