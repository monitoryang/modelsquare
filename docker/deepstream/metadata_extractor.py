"""Detection metadata extractor for DeepStream pipelines.

This module provides BatchMetadataOperator subclasses that extract
detection statistics from DeepStream's inference output and publish
them to Redis for the WebSocket layer to consume.

Classes:
    TrackingIDMapper - Maps global tracker IDs to per-class sequential IDs.
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
from typing import Any, Deque, Dict, List, Optional

import redis
from pyservicemaker import BatchMetadataOperator

logger = logging.getLogger(__name__)


class TrackingIDMapper:
    """Map global tracker IDs to per-class sequential IDs.

    The NvDCF tracker assigns global unique IDs across all classes.
    This mapper converts them to per-class counters so each class
    starts from 1 independently (e.g., person#1, person#2, car#1).
    """

    UNTRACKED = 0xFFFFFFFFFFFFFFFF  # DeepStream UNTRACKED_OBJECT_ID

    def __init__(self):
        self._class_counters: Dict[int, int] = {}
        self._global_to_local: Dict[tuple, int] = {}

    def get_local_id(self, class_id: int, global_id: int) -> Optional[int]:
        """Return the per-class sequential ID for a tracked object.

        Returns None if the object is untracked.
        """
        if global_id == self.UNTRACKED:
            return None
        key = (class_id, global_id)
        if key not in self._global_to_local:
            counter = self._class_counters.get(class_id, 0) + 1
            self._class_counters[class_id] = counter
            self._global_to_local[key] = counter
        return self._global_to_local[key]


class IOUTracker:
    """Lightweight IOU-based tracker for OWL detections.

    OWL (open-vocabulary detection) produces per-frame independent detections
    that may vary significantly in position between frames. The GPU-based
    NvDCF tracker is too strict for OWL, so we use this simple Python-based
    tracker that associates detections by IOU overlap with per-class matching.

    Each class maintains independent track IDs starting from 1.
    """

    def __init__(self, iou_threshold: float = 0.2, max_age: int = 15):
        self._iou_threshold = iou_threshold
        self._max_age = max_age
        # Per-class state
        self._tracks: Dict[int, List[dict]] = {}  # class_id -> [track, ...]
        self._class_counters: Dict[int, int] = {}  # class_id -> next_id

    @staticmethod
    def _iou(box_a: List[float], box_b: List[float]) -> float:
        """Compute IoU between two boxes [x1, y1, x2, y2]."""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def update(
        self, detections: List[Dict[str, Any]]
    ) -> List[Optional[int]]:
        """Associate current detections with existing tracks.

        Args:
            detections: List of dicts with keys 'class_id' and 'box' ([x1,y1,x2,y2]).

        Returns:
            List of per-class track IDs (parallel to input detections).
            Returns None for detections that could not be tracked.
        """
        # Group detections by class
        class_dets: Dict[int, List[int]] = {}
        for i, det in enumerate(detections):
            cid = det["class_id"]
            class_dets.setdefault(cid, []).append(i)

        result: List[Optional[int]] = [None] * len(detections)

        for class_id, det_indices in class_dets.items():
            if class_id not in self._tracks:
                self._tracks[class_id] = []
            if class_id not in self._class_counters:
                self._class_counters[class_id] = 0

            tracks = self._tracks[class_id]
            det_boxes = [detections[i]["box"] for i in det_indices]

            # Compute IOU matrix between tracks and detections
            matched_tracks = set()
            matched_dets = set()

            # Greedy matching: best IOU first
            pairs = []
            for ti, track in enumerate(tracks):
                for di, box in enumerate(det_boxes):
                    iou_val = self._iou(track["box"], box)
                    if iou_val >= self._iou_threshold:
                        pairs.append((iou_val, ti, di))
            pairs.sort(key=lambda x: x[0], reverse=True)

            for iou_val, ti, di in pairs:
                if ti in matched_tracks or di in matched_dets:
                    continue
                matched_tracks.add(ti)
                matched_dets.add(di)
                # Update track
                tracks[ti]["box"] = det_boxes[di]
                tracks[ti]["age"] = 0
                result[det_indices[di]] = tracks[ti]["id"]

            # Create new tracks for unmatched detections
            for di in range(len(det_boxes)):
                if di in matched_dets:
                    continue
                self._class_counters[class_id] += 1
                new_id = self._class_counters[class_id]
                tracks.append({"id": new_id, "box": det_boxes[di], "age": 0})
                result[det_indices[di]] = new_id

            # Age unmatched tracks and remove old ones
            for ti in range(len(tracks) - 1, -1, -1):
                if ti not in matched_tracks and tracks[ti]["age"] <= self._max_age:
                    tracks[ti]["age"] += 1
            self._tracks[class_id] = [
                t for t in tracks if t["age"] <= self._max_age
            ]

        return result


class DetectionStatsExtractor(BatchMetadataOperator):
    """Extract detection statistics from nvinferserver output and publish to Redis.

    This operator is attached as a Probe to the pipeline after the tracker
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
        self._id_mapper = TrackingIDMapper()

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
    scores, labels, track_ids) to Redis and accumulates them in memory for
    final JSON serialization when the pipeline reaches EOS.
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
        self._id_mapper = TrackingIDMapper()
        self._iou_tracker = IOUTracker()

    def handle_metadata(self, batch_meta: Any) -> None:
        """Called per batch by DeepStream pipeline thread.

        Extracts full bounding box data and tracking IDs from each frame
        and publishes to Redis without rate limiting. Also updates progress
        periodically.

        Supports two tracking modes:
        - If nvtracker is in the pipeline: uses TrackingIDMapper to convert
          global tracker IDs to per-class sequential IDs.
        - If no nvtracker (OWL pipelines): uses IOUTracker to perform
          Python-based frame-to-frame association.
        """
        for frame_meta in batch_meta.frame_items:
            self.frames_processed += 1
            boxes: List[List[float]] = []
            scores: List[float] = []
            labels: List[int] = []
            class_names_list: List[str] = []

            # Collect raw detections
            raw_dets = []
            for obj in frame_meta.object_items:
                r = obj.rect_params
                box = [
                    round(r.left, 2),
                    round(r.top, 2),
                    round(r.left + r.width, 2),
                    round(r.top + r.height, 2),
                ]
                boxes.append(box)
                scores.append(round(obj.confidence, 4))
                labels.append(obj.class_id)
                name = (
                    self._labels[obj.class_id]
                    if obj.class_id < len(self._labels)
                    else f"class_{obj.class_id}"
                )
                class_names_list.append(name)
                raw_dets.append({
                    "class_id": obj.class_id,
                    "box": box,
                    "object_id": obj.object_id,
                })

            # Determine tracking mode based on whether nvtracker set IDs
            track_ids: List[Optional[int]] = []
            if raw_dets and raw_dets[0]["object_id"] != TrackingIDMapper.UNTRACKED:
                # nvtracker is present — use TrackingIDMapper
                for det in raw_dets:
                    local_id = self._id_mapper.get_local_id(
                        det["class_id"], det["object_id"]
                    )
                    track_ids.append(local_id)
                # Rewrite display_text with per-class IDs (nvtracker's
                # display-tracking-id shows global IDs which are not per-class)
                try:
                    for i, obj in enumerate(frame_meta.object_items):
                        if i < len(track_ids) and track_ids[i] is not None:
                            name = (
                                class_names_list[i]
                                if i < len(class_names_list)
                                else f"class_{obj.class_id}"
                            )
                            conf_pct = int(obj.confidence * 100)
                            obj.text_params.display_text = (
                                f"{name}#{track_ids[i]} {conf_pct}%"
                            )
                except (AttributeError, TypeError) as e:
                    if not getattr(self, "_text_params_warned", False):
                        logger.warning(
                            "Cannot modify display_text via pyservicemaker: %s", e
                        )
                        self._text_params_warned = True
            else:
                # No nvtracker — use Python IOUTracker
                track_ids = self._iou_tracker.update(raw_dets)
                # Update display_text on each object so OSD renders the
                # tracking ID.  The probe fires before OSD processes the
                # metadata, so changes here are reflected in the rendered
                # video.
                try:
                    for i, obj in enumerate(frame_meta.object_items):
                        if i < len(track_ids) and track_ids[i] is not None:
                            name = (
                                class_names_list[i]
                                if i < len(class_names_list)
                                else f"class_{obj.class_id}"
                            )
                            conf_pct = int(obj.confidence * 100)
                            obj.text_params.display_text = (
                                f"{name}#{track_ids[i]} {conf_pct}%"
                            )
                except (AttributeError, TypeError) as e:
                    # pyservicemaker may not expose text_params — log once
                    if not getattr(self, "_text_params_warned", False):
                        logger.warning(
                            "Cannot modify display_text via pyservicemaker: %s", e
                        )
                        self._text_params_warned = True

            frame_result = {
                "frame_index": self.frames_processed - 1,
                "timestamp_ms": round(
                    ((self.frames_processed - 1) / self.fps) * 1000, 2
                ),
                "boxes": boxes,
                "scores": scores,
                "labels": labels,
                "class_names": class_names_list,
                "track_ids": track_ids,
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
