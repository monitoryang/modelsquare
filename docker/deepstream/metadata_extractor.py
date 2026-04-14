"""Detection metadata extractor for DeepStream pipelines.

This module provides the BatchMetadataOperator subclass that extracts
detection statistics from DeepStream's inference output and publishes
them to Redis for the WebSocket layer to consume.

Note: The actual implementation is embedded in pipeline_manager.py
as DetectionStatsExtractor. This module re-exports it and provides
additional utilities.
"""

import json
import logging
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
