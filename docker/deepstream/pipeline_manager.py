"""DeepStream 8.0 Pipeline Manager Service

FastAPI service that manages DeepStream GPU pipelines for real-time
video inference with OSD overlay and RTMP output.
"""

import asyncio
import json
import logging
import os
import signal
import tempfile
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from string import Template
from typing import Any, Deque, Dict, List, Optional

import redis
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# DeepStream 8.0 pyservicemaker imports
from pyservicemaker import BatchMetadataOperator, Pipeline, Probe

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Handle SIGABRT from C++ destructor cleanup in DeepStream / GStreamer runtime.
# When pipeline.stop() triggers C++ destructors, std::terminate() may be called,
# which invokes abort().  C abort() raises SIGABRT; if the handler returns,
# abort() resets the handler to SIG_DFL and re-raises -- killing the process with
# a core dump.  By calling os._exit() inside the handler we prevent the re-raise,
# avoid the core dump, and let Docker's restart policy bring the container back.
def _handle_sigabrt(signum, frame):
    logger.warning("Caught SIGABRT (C++ destructor cleanup) -- performing clean exit")
    os._exit(0)

signal.signal(signal.SIGABRT, _handle_sigabrt)

# Hold references to stopped Pipeline objects to prevent C++ destructor
# from being invoked by Python GC.  GStreamer / DeepStream Pipeline destructors
# can trigger std::terminate() → abort(), which kills the process.
# These references are cheap (the underlying GStreamer pipeline is already
# in NULL state after stop()), and are released on process exit.
_stopped_pipelines: list = []


# When the RTMP input stream drops, the GStreamer pipeline receives EOS from the
# RTMP source and dies permanently.  The auto-restart mechanism tears down the
# dead pipeline and recreates it so the next RTMP push is picked up automatically.
MAX_PIPELINE_RESTARTS = 10
RESTART_BASE_DELAY_S = 5
RESTART_STABLE_SECONDS = 60  # Reset restart counter after this many seconds of stability

# Environment configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
TRITON_URL = os.environ.get("TRITON_URL", "triton:8001")
SRS_RTMP_URL = os.environ.get("SRS_RTMP_URL", "rtmp://srs:1935")

# Template paths
TRITON_CONFIG_TEMPLATE = os.environ.get(
    "TRITON_CONFIG_TEMPLATE", "/app/config/triton_infer_template.txt"
)
TRITON_OWL_CONFIG_TEMPLATE = os.environ.get(
    "TRITON_OWL_CONFIG_TEMPLATE", "/app/config/triton_owl_infer_template.txt"
)


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


class PipelineCreateRequest(BaseModel):
    session_id: str
    model_type: str  # "yolo" or "owl"
    model_name: str
    triton_url: Optional[str] = None
    input_url: Optional[str] = None  # RTMP URL; auto-derived if empty
    class_names: List[str] = []
    class_colors: Dict[str, str] = {}
    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    # OWL-specific
    owl_prompts: Optional[List[str]] = None
    owl_variant: Optional[str] = None
    owl_text_embeddings: Optional[str] = None  # base64-encoded binary


class PipelineUpdateRequest(BaseModel):
    conf_threshold: Optional[float] = None
    iou_threshold: Optional[float] = None
    owl_prompts: Optional[List[str]] = None
    owl_text_embeddings: Optional[str] = None  # base64 for hot-reload
    class_names: Optional[List[str]] = None
    class_colors: Optional[Dict[str, str]] = None
    owl_prompts: Optional[List[str]] = None


# ------------------------------------------------------------------
# Detection stats extractor (BatchMetadataOperator)
# ------------------------------------------------------------------


class DetectionStatsExtractor(BatchMetadataOperator):
    """Extract detection statistics from nvinferserver output and publish to Redis."""

    def __init__(self, session_id: str, class_names: List[str],
                 class_colors: Dict[str, str], redis_client: redis.Redis):
        super().__init__()
        self.session_id = session_id
        self._labels = class_names
        self._class_colors = class_colors
        self._redis = redis_client
        self.frames_processed = 0
        self._latency_window: Deque[float] = deque(maxlen=100)
        self._last_publish_time = 0.0
        self._last_frame_time = 0.0

    def handle_metadata(self, batch_meta):
        """Called per batch by DeepStream pipeline thread."""
        now = time.time()
        for frame_meta in batch_meta.frame_items:
            detection_count = 0
            class_counts: Dict[str, int] = {}

            for obj in frame_meta.object_items:
                detection_count += 1
                class_id = obj.class_id
                name = self._labels[class_id] if class_id < len(self._labels) else f"class_{class_id}"
                class_counts[name] = class_counts.get(name, 0) + 1

            self.frames_processed += 1

            # Measure real pipeline throughput: time between consecutive frames
            if self._last_frame_time > 0:
                frame_interval_ms = (now - self._last_frame_time) * 1000
                self._latency_window.append(frame_interval_ms)
            self._last_frame_time = now

            # Rate-limit Redis publishes to at most 10 per second
            if now - self._last_publish_time < 0.1:
                continue
            self._last_publish_time = now

            avg_latency = (
                sum(self._latency_window) / len(self._latency_window)
                if self._latency_window else 0
            )

            result = {
                "type": "inference_result",
                "session_id": self.session_id,
                "frame_id": str(frame_meta.frame_number),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": avg_latency,
                "avg_latency_ms": avg_latency,
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


# ------------------------------------------------------------------
# Pipeline session wrapper
# ------------------------------------------------------------------


@dataclass
class PipelineSession:
    session_id: str
    model_type: str
    model_name: str
    pipeline: Optional[Pipeline] = None
    extractor: Optional[DetectionStatsExtractor] = None
    config_file: Optional[str] = None  # temp file path for nvinferserver config
    labels_file: Optional[str] = None  # temp file path for labels
    embeds_file: Optional[str] = None  # temp file path for OWL text embeddings
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Auto-restart state
    request: Optional[Any] = None  # Stored PipelineCreateRequest for recreation
    restart_count: int = 0
    _restarting: bool = False
    _stopped_intentionally: bool = False  # True when user explicitly stops

    def cleanup(self):
        """Stop pipeline and remove temp files.

        After stop(), the Pipeline C++ object is parked in a global list
        rather than released.  Releasing it triggers the C++ destructor
        chain which calls std::terminate() → abort() in GStreamer/DeepStream.
        Parking the reference avoids the crash; the objects are tiny (the
        underlying GStreamer pipeline is already in NULL state).
        """
        if self.pipeline:
            logger.info(f"Stopping pipeline for session {self.session_id} ...")
            stop_result = [False]
            pipeline_ref = self.pipeline  # hold a reference

            def _do_stop():
                try:
                    pipeline_ref.stop()
                    stop_result[0] = True
                except Exception as e:
                    logger.warning(f"Error stopping pipeline {self.session_id}: {e}")

            t = threading.Thread(target=_do_stop, daemon=True)
            t.start()
            t.join(timeout=10)  # Wait at most 10 seconds

            if stop_result[0]:
                logger.info(f"Pipeline stopped cleanly for session {self.session_id}")
            elif t.is_alive():
                logger.warning(
                    f"Pipeline stop timed out for {self.session_id}, "
                    f"abandoning (daemon thread will be cleaned up on exit)"
                )

            # Park the stopped pipeline to prevent C++ destructor from running.
            _stopped_pipelines.append(pipeline_ref)
            self.pipeline = None
        for tmp in (self.config_file, self.labels_file, self.embeds_file):
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
        self.config_file = None
        self.labels_file = None
        self.embeds_file = None


# ------------------------------------------------------------------
# Pipeline Manager
# ------------------------------------------------------------------


class PipelineManager:
    """Manages DeepStream pipeline lifecycle for all active sessions."""

    def __init__(self):
        self._sessions: Dict[str, PipelineSession] = {}
        self._redis: Optional[redis.Redis] = None
        self._lock = threading.Lock()

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(REDIS_URL, decode_responses=False)
        return self._redis

    def _render_triton_config(self, req: PipelineCreateRequest) -> str:
        """Render nvinferserver config template and write to a temp file.

        Returns:
            config_path
        """
        with open(TRITON_CONFIG_TEMPLATE, "r") as f:
            template = Template(f.read())

        rendered = template.safe_substitute(
            MODEL_NAME=req.model_name,
            TRITON_URL=req.triton_url or TRITON_URL,
            MAX_BATCH_SIZE=0,
        )

        fd, config_path = tempfile.mkstemp(suffix=".txt", prefix=f"ds_config_{req.session_id}_")
        with os.fdopen(fd, "w") as f:
            f.write(rendered)
        return config_path

    def create_pipeline(self, req: PipelineCreateRequest) -> PipelineSession:
        """Create and start a DeepStream pipeline for a session."""
        with self._lock:
            if req.session_id in self._sessions:
                raise ValueError(f"Pipeline already exists for session {req.session_id}")

        # Determine RTMP input URL
        input_url = req.input_url or f"{SRS_RTMP_URL}/live/{req.session_id}"
        # RTMP output URL (DeepStream pushes processed video back to SRS)
        output_url = f"{SRS_RTMP_URL}/output/{req.session_id}"

        redis_client = self._get_redis()

        if req.model_type == "yolo":
            session = self._build_yolo_pipeline(req, input_url, output_url, redis_client)
        elif req.model_type == "owl":
            session = self._build_owl_pipeline(req, input_url, output_url, redis_client)
        else:
            raise ValueError(f"Unknown model_type: {req.model_type}")

        # Store the original request so the pipeline can be recreated on
        # source disconnection (EOS / ERROR).
        session.request = req

        # Start the pipeline
        def _on_message(msg):
            """Handle GStreamer bus messages from the pipeline."""
            msg_str = str(msg) if msg else ""
            if "ERROR" in msg_str:
                logger.error(f"Pipeline error for {req.session_id}: {msg_str}")
                self._schedule_restart(req.session_id)
            elif "EOS" in msg_str:
                logger.warning(f"Pipeline EOS for {req.session_id}: {msg_str}")
                self._schedule_restart(req.session_id)
            else:
                logger.debug(f"Pipeline message for {req.session_id}: {msg_str}")

        try:
            session.pipeline.start(on_message=_on_message)
            logger.info(
                f"Pipeline started for session {req.session_id} "
                f"(type={req.model_type}, input={input_url}, output={output_url})"
            )
        except Exception as e:
            session.cleanup()
            raise RuntimeError(f"Failed to start pipeline: {e}") from e

        with self._lock:
            self._sessions[req.session_id] = session

        return session

    def _write_labels_file(self, req: PipelineCreateRequest) -> str:
        """Write a labels+colors file for the C++ custom parser.

        Format: one line per class — ``name #RRGGBB``
        Returns the temp file path.
        """
        fd, labels_path = tempfile.mkstemp(
            suffix=".txt", prefix=f"ds_labels_{req.session_id}_"
        )
        with os.fdopen(fd, "w") as f:
            for name in req.class_names:
                color = req.class_colors.get(name, "#00FF00")
                f.write(f"{name} {color}\n")
        return labels_path

    def _write_embeddings_file(self, b64_data: str, session_id: str) -> str:
        """Decode base64 text embeddings and write to a binary temp file.

        Binary format: [int32 num_classes][int32 embed_dim][float32 * N * D]
        Returns the temp file path.
        """
        import base64

        raw = base64.b64decode(b64_data)
        fd, embeds_path = tempfile.mkstemp(
            suffix=".bin", prefix=f"ds_embeds_{session_id}_"
        )
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        return embeds_path

    def _render_owl_config(self, req: PipelineCreateRequest) -> str:
        """Render OWL nvinferserver config template and write to a temp file."""
        with open(TRITON_OWL_CONFIG_TEMPLATE, "r") as f:
            template = Template(f.read())

        rendered = template.safe_substitute(
            MODEL_NAME=req.model_name,
            TRITON_URL=req.triton_url or TRITON_URL,
            MAX_BATCH_SIZE=0,
        )

        fd, config_path = tempfile.mkstemp(
            suffix=".txt", prefix=f"ds_owl_config_{req.session_id}_"
        )
        with os.fdopen(fd, "w") as f:
            f.write(rendered)
        return config_path

    def _build_yolo_pipeline(
        self,
        req: PipelineCreateRequest,
        input_url: str,
        output_url: str,
        redis_client: redis.Redis,
    ) -> PipelineSession:
        """Build a YOLO detection pipeline with nvinferserver + OSD + RTMP output."""
        labels_path = self._write_labels_file(req)
        # Set env var so the C++ custom parser can find the labels file.
        # The factory function CreateInferServerCustomProcess reads DS_LABELS_FILE
        # at instantiation time during pipeline.start().
        os.environ["DS_LABELS_FILE"] = labels_path
        config_path = self._render_triton_config(req)

        pipeline = Pipeline(f"ds-{req.session_id}")

        # Source: pull RTMP from SRS (GPU NVDEC decode)
        pipeline.add("nvurisrcbin", "src", {"uri": input_url})

        # Batch processing — new nvstreammux (USE_NEW_NVSTREAMMUX=yes)
        # preserves the original source resolution; no width/height needed.
        pipeline.add("nvstreammux", "mux", {
            "batch-size": 1,
            "batched-push-timeout": 40000,
            "live-source": 1,
        })

        # Inference via external Triton gRPC
        pipeline.add("nvinferserver", "infer", {
            "config-file-path": config_path,
        })

        # OSD: burn detection boxes into video
        pipeline.add("nvvideoconvert", "conv1")
        pipeline.add("nvdsosd", "osd")

        # GPU encode -> RTMP push to SRS
        # capsfilter is required to negotiate I420 format for the hardware encoder
        pipeline.add("nvvideoconvert", "conv2")
        pipeline.add("capsfilter", "caps", {
            "caps": "video/x-raw(memory:NVMM), format=I420",
        })
        pipeline.add("nvv4l2h264enc", "encoder", {
            "bitrate": 4000000,
            "idrinterval": 30,  # IDR every 30 frames (~1s at 30fps) for HLS segmenting
        })
        pipeline.add("h264parse", "parser", {"config-interval": -1})
        pipeline.add("flvmux", "muxer", {"streamable": True})
        pipeline.add("rtmpsink", "sink", {"location": output_url})

        # Link elements
        pipeline.link("src", "mux")
        pipeline.link(
            "mux", "infer", "conv1", "osd", "conv2", "caps",
            "encoder", "parser", "muxer", "sink",
        )

        # Attach metadata extraction probe after inference
        extractor = DetectionStatsExtractor(
            session_id=req.session_id,
            class_names=req.class_names,
            class_colors=req.class_colors,
            redis_client=redis_client,
        )
        pipeline.attach("infer", Probe("stats", extractor))

        return PipelineSession(
            session_id=req.session_id,
            model_type="yolo",
            model_name=req.model_name,
            pipeline=pipeline,
            extractor=extractor,
            config_file=config_path,
            labels_file=labels_path,
        )

    def _build_owl_pipeline(
        self,
        req: PipelineCreateRequest,
        input_url: str,
        output_url: str,
        redis_client: redis.Redis,
    ) -> PipelineSession:
        """Build an OWL detection pipeline with nvinferserver + OSD + RTMP output.

        Uses the OWL image encoder on Triton for per-frame inference.
        Text embeddings are pre-computed by the backend and passed via
        ``owl_text_embeddings`` (base64-encoded binary).  The C++ custom
        parser reads them from a file to compute cosine similarity.
        """
        if not req.owl_text_embeddings:
            raise ValueError("OWL pipeline requires owl_text_embeddings")

        # Write labels + embeddings files for the C++ parser
        labels_path = self._write_labels_file(req)
        embeds_path = self._write_embeddings_file(
            req.owl_text_embeddings, req.session_id
        )

        # Set env vars so the C++ OWL parser can find the files
        os.environ["DS_LABELS_FILE"] = labels_path
        os.environ["DS_OWL_EMBEDS_FILE"] = embeds_path

        config_path = self._render_owl_config(req)

        pipeline = Pipeline(f"ds-owl-{req.session_id}")

        # Source: pull RTMP from SRS (GPU NVDEC decode)
        pipeline.add("nvurisrcbin", "src", {"uri": input_url})

        # Batch processing — new nvstreammux preserves source resolution
        pipeline.add("nvstreammux", "mux", {
            "batch-size": 1,
            "batched-push-timeout": 40000,
            "live-source": 1,
        })

        # Inference via external Triton gRPC (OWL image encoder)
        pipeline.add("nvinferserver", "infer", {
            "config-file-path": config_path,
        })

        # OSD: burn detection boxes into video
        pipeline.add("nvvideoconvert", "conv1")
        pipeline.add("nvdsosd", "osd")

        # GPU encode -> RTMP push to SRS
        pipeline.add("nvvideoconvert", "conv2")
        pipeline.add("capsfilter", "caps", {
            "caps": "video/x-raw(memory:NVMM), format=I420",
        })
        pipeline.add("nvv4l2h264enc", "encoder", {
            "bitrate": 4000000,
            "idrinterval": 30,
        })
        pipeline.add("h264parse", "parser", {"config-interval": -1})
        pipeline.add("flvmux", "muxer", {"streamable": True})
        pipeline.add("rtmpsink", "sink", {"location": output_url})

        # Link elements
        pipeline.link("src", "mux")
        pipeline.link(
            "mux", "infer", "conv1", "osd", "conv2", "caps",
            "encoder", "parser", "muxer", "sink",
        )

        # Attach metadata extraction probe after inference
        extractor = DetectionStatsExtractor(
            session_id=req.session_id,
            class_names=req.class_names or [],
            class_colors=req.class_colors or {},
            redis_client=redis_client,
        )
        pipeline.attach("infer", Probe("stats", extractor))

        return PipelineSession(
            session_id=req.session_id,
            model_type="owl",
            model_name=req.model_name,
            pipeline=pipeline,
            extractor=extractor,
            config_file=config_path,
            labels_file=labels_path,
            embeds_file=embeds_path,
        )

    # ------------------------------------------------------------------
    # Auto-restart on source disconnection (EOS / ERROR)
    # ------------------------------------------------------------------

    def _schedule_restart(self, session_id: str):
        """Schedule pipeline restart in a background thread.

        Called from GStreamer's bus-message callback when the source
        disconnects (EOS) or an unrecoverable error is reported.
        Must return quickly -- actual work happens in _do_restart().
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session._restarting or session._stopped_intentionally:
                return
            if not session.request:
                logger.warning(f"Cannot restart {session_id}: no stored request")
                return
            if session.restart_count >= MAX_PIPELINE_RESTARTS:
                logger.error(
                    f"Max restarts ({MAX_PIPELINE_RESTARTS}) reached for "
                    f"{session_id}, removing pipeline"
                )
                self._sessions.pop(session_id, None)
                return
            session._restarting = True

        threading.Thread(
            target=self._do_restart,
            args=(session_id,),
            daemon=True,
            name=f"restart-{session_id[:8]}",
        ).start()

    def _do_restart(self, session_id: str):
        """Tear down the dead pipeline and recreate it (background thread)."""
        with self._lock:
            session = self._sessions.get(session_id)
        if not session or not session.request:
            return

        attempt = session.restart_count + 1
        delay = min(RESTART_BASE_DELAY_S * attempt, 30)
        logger.info(
            f"Restarting pipeline {session_id} "
            f"(attempt {attempt}/{MAX_PIPELINE_RESTARTS}) in {delay}s ..."
        )
        time.sleep(delay)

        stored_request = session.request

        # Remove old session from registry (so create_pipeline won't raise
        # "already exists").
        with self._lock:
            self._sessions.pop(session_id, None)

        # Stop old pipeline and park the reference to avoid C++ destructor crash.
        old_pipeline = session.pipeline
        session.pipeline = None
        if old_pipeline:
            try:
                old_pipeline.stop()
            except Exception as e:
                logger.warning(f"Error stopping old pipeline during restart: {e}")
            _stopped_pipelines.append(old_pipeline)

        # Clean up temp files from old session
        for tmp in (session.config_file, session.labels_file, session.embeds_file):
            if tmp and os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        # Try to create a fresh pipeline
        try:
            new_session = self.create_pipeline(stored_request)
            new_session.restart_count = attempt
            logger.info(
                f"Pipeline restarted successfully for {session_id} "
                f"(attempt {attempt})"
            )
            # Start a stability timer: if the pipeline runs for
            # RESTART_STABLE_SECONDS without another EOS/ERROR, reset
            # the restart counter so future drops get the full retry budget.
            threading.Thread(
                target=self._reset_restart_count_after_stable,
                args=(session_id, attempt),
                daemon=True,
            ).start()
        except Exception as e:
            logger.error(
                f"Pipeline restart failed for {session_id} "
                f"(attempt {attempt}): {e}"
            )
            # Park a placeholder so future restart attempts can proceed
            placeholder = PipelineSession(
                session_id=session_id,
                model_type=stored_request.model_type,
                model_name=stored_request.model_name,
                request=stored_request,
                restart_count=attempt,
                _restarting=False,
            )
            with self._lock:
                if session_id not in self._sessions:
                    self._sessions[session_id] = placeholder
            # Schedule another attempt
            self._schedule_restart(session_id)

    def _reset_restart_count_after_stable(self, session_id: str, at_attempt: int):
        """Reset restart_count to 0 if the pipeline survives long enough."""
        time.sleep(RESTART_STABLE_SECONDS)
        with self._lock:
            session = self._sessions.get(session_id)
            if session and session.restart_count == at_attempt:
                logger.info(
                    f"Pipeline {session_id} stable for {RESTART_STABLE_SECONDS}s, "
                    f"resetting restart counter"
                )
                session.restart_count = 0

    # ------------------------------------------------------------------
    # Pipeline lifecycle
    # ------------------------------------------------------------------

    def stop_pipeline(self, session_id: str) -> None:
        """Stop and destroy a pipeline."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            # Mark as intentionally stopped so _schedule_restart ignores
            # any in-flight EOS/ERROR callbacks from the dying pipeline.
            session._stopped_intentionally = True
            session.cleanup()
            logger.info(f"Pipeline stopped for session {session_id}")
        else:
            logger.warning(f"No pipeline found for session {session_id}")

    def get_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline statistics."""
        with self._lock:
            session = self._sessions.get(session_id)
        if not session or not session.extractor:
            return None
        ext = session.extractor
        return {
            "session_id": session_id,
            "model_type": session.model_type,
            "model_name": session.model_name,
            "frames_processed": ext.frames_processed,
            "avg_latency_ms": (
                sum(ext._latency_window) / len(ext._latency_window)
                if ext._latency_window else 0
            ),
            "created_at": session.created_at.isoformat(),
        }

    def list_pipelines(self) -> List[Dict[str, Any]]:
        """List all active pipelines."""
        with self._lock:
            return [
                {
                    "session_id": sid,
                    "model_type": s.model_type,
                    "model_name": s.model_name,
                    "frames_processed": s.extractor.frames_processed if s.extractor else 0,
                    "created_at": s.created_at.isoformat(),
                }
                for sid, s in self._sessions.items()
            ]

    def stop_all(self) -> None:
        """Stop all pipelines (used during shutdown)."""
        with self._lock:
            session_ids = list(self._sessions.keys())
        for sid in session_ids:
            self.stop_pipeline(sid)


# ------------------------------------------------------------------
# FastAPI application
# ------------------------------------------------------------------

manager = PipelineManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DeepStream Pipeline Manager starting...")
    yield
    logger.info("Shutting down all pipelines...")
    manager.stop_all()


app = FastAPI(title="DeepStream Pipeline Manager", lifespan=lifespan)


@app.post("/pipelines")
async def create_pipeline(req: PipelineCreateRequest):
    try:
        session = await asyncio.to_thread(manager.create_pipeline, req)
        return {
            "status": "ok",
            "session_id": session.session_id,
            "output_url": f"{SRS_RTMP_URL}/output/{req.session_id}",
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/pipelines/{session_id}")
async def delete_pipeline(session_id: str):
    await asyncio.to_thread(manager.stop_pipeline, session_id)
    return {"status": "ok", "session_id": session_id}


@app.patch("/pipelines/{session_id}")
async def update_pipeline(session_id: str, req: PipelineUpdateRequest):
    """Update inference parameters for a running pipeline.

    For threshold changes we regenerate the nvinferserver config file in-place
    and set the config-file-path property again which triggers a reload.
    For OWL prompt changes we atomically replace the embeddings/labels files.
    """
    with manager._lock:
        session = manager._sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    updated_fields = []

    # Threshold update -- only meaningful for YOLO pipelines with nvinferserver
    if session.config_file and (req.conf_threshold is not None or req.iou_threshold is not None):
        try:
            # Read current config, patch threshold values, write back
            with open(session.config_file, "r") as f:
                content = f.read()

            import re
            if req.conf_threshold is not None:
                content = re.sub(
                    r"confidence_threshold:\s*[\d.]+",
                    f"confidence_threshold: {req.conf_threshold}",
                    content,
                )
                updated_fields.append("conf_threshold")
            if req.iou_threshold is not None:
                content = re.sub(
                    r"iou_threshold:\s*[\d.]+",
                    f"iou_threshold: {req.iou_threshold}",
                    content,
                )
                updated_fields.append("iou_threshold")

            with open(session.config_file, "w") as f:
                f.write(content)

            # Trigger nvinferserver to reload the config
            if session.pipeline:
                try:
                    session.pipeline.set_property(
                        "infer", "config-file-path", session.config_file
                    )
                except Exception as e:
                    logger.warning(f"Could not hot-reload nvinferserver config: {e}")
        except Exception as e:
            logger.error(f"Failed to update config for {session_id}: {e}")

    # OWL embeddings + labels hot-reload: write new files atomically.
    # The C++ parser checks file mtime each frame and reloads when changed.
    logger.info(
        f"PATCH {session_id}: owl_text_embeddings={'set' if req.owl_text_embeddings else 'None'}, "
        f"embeds_file={session.embeds_file}, class_names={req.class_names}"
    )
    if req.owl_text_embeddings is not None and session.embeds_file:
        try:
            import base64

            raw = base64.b64decode(req.owl_text_embeddings)
            tmp_path = session.embeds_file + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(raw)
            os.replace(tmp_path, session.embeds_file)
            updated_fields.append("owl_text_embeddings")
            logger.info(f"OWL embeddings hot-reloaded for {session_id}")
        except Exception as e:
            logger.error(f"Failed to update OWL embeddings for {session_id}: {e}")

    if req.class_names is not None and session.labels_file:
        try:
            colors = req.class_colors or {}
            tmp_path = session.labels_file + ".tmp"
            with open(tmp_path, "w") as f:
                for name in req.class_names:
                    color = colors.get(name, "#00FF00")
                    f.write(f"{name} {color}\n")
            os.replace(tmp_path, session.labels_file)
            updated_fields.append("class_names")

            # Update extractor labels for Redis stats
            if session.extractor:
                session.extractor._labels = req.class_names
                session.extractor._class_colors = colors
        except Exception as e:
            logger.error(f"Failed to update labels for {session_id}: {e}")

    if req.owl_prompts is not None and "owl_text_embeddings" not in updated_fields:
        updated_fields.append("owl_prompts")

    return {"status": "ok", "session_id": session_id, "updated": updated_fields}


@app.get("/pipelines/{session_id}/stats")
async def get_pipeline_stats(session_id: str):
    stats = manager.get_stats(session_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return stats


@app.get("/pipelines")
async def list_pipelines():
    return manager.list_pipelines()


@app.get("/health")
async def health():
    return {"status": "ok", "pipelines": len(manager._sessions)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
