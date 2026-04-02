"""Real-time stream inference service

Consumes frames from Redis Stream, runs inference via Triton,
and publishes results for WebSocket delivery.
"""

import asyncio
import io
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Set

import numpy as np
from PIL import Image

from app.core.model_adapter import OwlModelAdapter, YOLOModelAdapter
from app.core.redis import get_redis_pool, get_redis_raw
from app.core.triton_repository import triton_repository

logger = logging.getLogger(__name__)


@dataclass
class StreamSession:
    """Active stream session info"""
    session_id: str
    model_id: str
    stream_name: str
    class_names: List[str]
    class_colors: Dict[str, str]
    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    frames_processed: int = 0
    # Use a fixed-size sliding window (last 100 frames) instead of an ever-growing
    # accumulator.  This prevents total_latency_ms from growing without bound and
    # keeps the deque size constant regardless of session duration.
    _latency_window: Deque[float] = field(
        default_factory=lambda: deque(maxlen=100)
    )
    last_result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # OWL-specific fields
    owl_text_prompts: Optional[List[str]] = None
    owl_variant: Optional[str] = None
    owl_text_embeds: Optional[Any] = None  # np.ndarray, cached once per session
    # Unified model adapter (set during session start)
    adapter: Optional[Any] = None  # ModelAdapter instance

    @property
    def total_latency_ms(self) -> float:
        """Total latency kept for backward compatibility (sum of window)."""
        return sum(self._latency_window)

    @property
    def avg_latency_ms(self) -> float:
        """Rolling average latency over the last 100 frames."""
        if not self._latency_window:
            return 0.0
        return sum(self._latency_window) / len(self._latency_window)


class StreamInferenceService:
    """Service for real-time stream inference"""

    def __init__(self):
        self._active_sessions: Dict[str, StreamSession] = {}
        self._result_callbacks: Dict[str, Set[Callable]] = {}
        self._consumer_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    async def start_session(
        self,
        session_id: str,
        model_id: str,
        stream_name: str,
        class_names: List[str],
        class_colors: Dict[str, str],
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        owl_text_prompts: Optional[List[str]] = None,
        owl_variant: Optional[str] = None,
    ) -> StreamSession:
        """Start a new inference session for a stream"""
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]

        session = StreamSession(
            session_id=session_id,
            model_id=model_id,
            stream_name=stream_name,
            class_names=class_names,
            class_colors=class_colors,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
            owl_text_prompts=owl_text_prompts,
            owl_variant=owl_variant,
        )

        # Build a unified adapter for this session and prepare it
        if owl_text_prompts and owl_variant:
            adapter = OwlModelAdapter(text_prompts=owl_text_prompts, owl_variant=owl_variant)
        else:
            triton_model_name = triton_repository.get_triton_model_name(model_id)
            adapter = YOLOModelAdapter(triton_model_name=triton_model_name, class_names=class_names)
        await adapter.prepare()
        session.adapter = adapter

        # Keep legacy fields in sync for backward compat
        if owl_text_prompts and owl_variant and isinstance(adapter, OwlModelAdapter):
            session.owl_text_embeds = adapter.text_embeds

        self._active_sessions[session_id] = session
        self._result_callbacks[session_id] = set()

        # Start consumer task for this session
        task = asyncio.create_task(self._consume_frames(session_id))
        self._consumer_tasks[session_id] = task

        logger.info(f"Started inference session {session_id} for stream {stream_name}")
        return session

    async def stop_session(self, session_id: str) -> None:
        """Stop an inference session"""
        if session_id not in self._active_sessions:
            return

        # Cancel consumer task
        if session_id in self._consumer_tasks:
            task = self._consumer_tasks.pop(session_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Cleanup
        self._active_sessions.pop(session_id, None)
        self._result_callbacks.pop(session_id, None)

        logger.info(f"Stopped inference session {session_id}")

    async def stop_all_sessions(self) -> None:
        """Stop all active inference sessions (used during startup cleanup)"""
        session_ids = list(self._active_sessions.keys())
        for session_id in session_ids:
            await self.stop_session(session_id)
        logger.info(f"Stopped all {len(session_ids)} inference sessions")

    def register_callback(self, session_id: str, callback: Callable) -> None:
        """Register a callback for inference results"""
        if session_id in self._result_callbacks:
            self._result_callbacks[session_id].add(callback)

    def unregister_callback(self, session_id: str, callback: Callable) -> None:
        """Unregister a callback"""
        if session_id in self._result_callbacks:
            self._result_callbacks[session_id].discard(callback)

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get session info"""
        return self._active_sessions.get(session_id)

    async def _consume_frames(self, session_id: str) -> None:
        """Consume frames from Redis Stream and run inference.

        Uses the *raw* (non-decoding) Redis client because the FFmpeg worker
        stores raw binary pixel data in the ``data`` field.  The default
        Redis client has ``decode_responses=True`` which would raise
        ``UnicodeDecodeError`` on the binary payload.
        """
        session = self._active_sessions.get(session_id)
        if not session:
            return

        # CRITICAL: use raw client to avoid UnicodeDecodeError on binary
        # frame data written by the FFmpeg worker.
        raw_redis = await get_redis_raw()
        stream_key = f"stream:{session.stream_name}"
        last_id = b"$"  # Only get new messages

        logger.info(f"Starting frame consumer for session {session_id}, stream {stream_key}")

        try:
            while session_id in self._active_sessions:
                try:
                    # Read from Redis Stream with timeout
                    messages = await raw_redis.xread(
                        {stream_key: last_id},
                        count=1,
                        block=1000  # 1 second timeout
                    )

                    if not messages:
                        continue

                    for stream_name, stream_messages in messages:
                        for msg_id, msg_data in stream_messages:
                            last_id = msg_id

                            # Decode bytes keys/values from raw client,
                            # keeping 'data' as raw bytes.
                            decoded = {}
                            for k, v in msg_data.items():
                                key = k.decode() if isinstance(k, bytes) else k
                                if key == "data":
                                    decoded[key] = v  # keep raw bytes
                                else:
                                    decoded[key] = (
                                        v.decode() if isinstance(v, bytes) else v
                                    )

                            # Process frame
                            await self._process_frame(session_id, decoded)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error consuming frame for session {session_id}: {e}")
                    await asyncio.sleep(0.1)  # Brief delay before retry

        except asyncio.CancelledError:
            logger.info(f"Frame consumer cancelled for session {session_id}")

    async def _process_frame(self, session_id: str, frame_data: Dict[str, Any]) -> None:
        """Process a single frame through inference"""
        session = self._active_sessions.get(session_id)
        if not session:
            return

        start_time = time.time()

        try:
            # Decode frame metadata
            frame_id = frame_data.get("frame_id", "0")
            width = int(frame_data.get("width", 640))
            height = int(frame_data.get("height", 480))
            raw_data = frame_data.get("data", b"")

            if not raw_data:
                return

            # Support both raw bytes (new path) and legacy hex strings.
            # The FFmpeg worker now writes raw bytes directly; hex fallback is
            # kept only for backward compatibility during rolling upgrades.
            if isinstance(raw_data, (bytes, bytearray)):
                raw_bytes = raw_data
            else:
                raw_bytes = bytes.fromhex(raw_data)

            # Build JPEG bytes for inference.
            # Use `with` so the BytesIO buffer is closed and its memory
            # released immediately after .getvalue() — without this the
            # buffer lingers until the next GC cycle, causing ~1.8 MB of
            # unreferenced memory per frame under 10 fps load.
            img_array = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((height, width, 3))
            pil_image = Image.fromarray(img_array, mode="RGB")
            with io.BytesIO() as img_buffer:
                pil_image.save(img_buffer, format="JPEG", quality=85)
                image_bytes = img_buffer.getvalue()

            # Explicitly release large intermediate objects before the
            # (potentially slow) async inference call so the GC can reclaim
            # memory sooner rather than waiting until after the await.
            del img_array, pil_image, raw_bytes

            # Dispatch inference via unified adapter
            detection_result = await session.adapter.infer_frame(
                image_bytes=image_bytes,
                conf_threshold=session.conf_threshold,
                iou_threshold=session.iou_threshold,
            )

            del image_bytes  # free JPEG buffer after inference

            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000

            # Update session stats using the fixed-size sliding window
            session.frames_processed += 1
            session._latency_window.append(latency_ms)

            # Build result
            result = {
                "session_id": session_id,
                "frame_id": frame_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": latency_ms,
                "avg_latency_ms": session.avg_latency_ms,
                "frames_processed": session.frames_processed,
                "detections": {
                    "boxes": detection_result.get("boxes", []),
                    "scores": detection_result.get("scores", []),
                    "class_names": detection_result.get("class_names", []),
                },
                "class_colors": session.class_colors,
                "image_size": {"width": width, "height": height},
            }

            session.last_result = result

            # Store latest result in Redis for polling clients
            await self._store_result(session_id, result)

            # Notify all registered callbacks
            await self._notify_callbacks(session_id, result)

        except Exception as e:
            logger.error(f"Error processing frame for session {session_id}: {e}")

    async def _store_result(self, session_id: str, result: Dict[str, Any]) -> None:
        """Store latest result in Redis"""
        redis = await get_redis_pool()
        result_key = f"stream_result:{session_id}:latest"

        # Store as JSON string
        await redis.setex(
            result_key,
            3600,  # 1 hour TTL
            json.dumps(result)
        )

        # Also publish to a channel for real-time subscribers
        channel = f"stream_results:{session_id}"
        await redis.publish(channel, json.dumps(result))

    async def _notify_callbacks(self, session_id: str, result: Dict[str, Any]) -> None:
        """Notify all registered callbacks with the result"""
        callbacks = self._result_callbacks.get(session_id, set())

        for callback in callbacks.copy():
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                logger.error(f"Error in callback for session {session_id}: {e}")

    async def get_latest_result(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest inference result for a session"""
        session = self._active_sessions.get(session_id)
        if session:
            return session.last_result

        # Try to get from Redis
        redis = await get_redis_pool()
        result_key = f"stream_result:{session_id}:latest"
        result_json = await redis.get(result_key)

        if result_json:
            return json.loads(result_json)

        return None


# Global singleton instance
stream_inference_service = StreamInferenceService()
