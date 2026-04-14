"""Streaming session endpoints with WebSocket support for real-time inference"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis, get_redis_pool
from app.models.model import Model
from app.models.user import User
from app.schemas.inference import (
    StreamSessionCreate,
    StreamSessionResponse,
    StreamStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# DeepStream pipeline manager internal URL (within Docker network)
DEEPSTREAM_API_URL = settings.DEEPSTREAM_API_URL


async def notify_deepstream_stop(session_id: str):
    """Notify DeepStream service to stop a pipeline for a session"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.delete(f"{DEEPSTREAM_API_URL}/pipelines/{session_id}")
            if resp.status_code == 200:
                logger.info(f"DeepStream pipeline stopped for {session_id}")
            else:
                logger.warning(f"DeepStream stop returned {resp.status_code} for {session_id}")
    except Exception as e:
        logger.debug(f"Could not notify DeepStream for {session_id}: {e}")


async def cleanup_expired_sessions():
    """Background task to clean up expired stream sessions"""
    redis = await get_redis_pool()
    if not redis:
        return

    cleaned = 0

    # Get all user session sets
    user_session_keys = await redis.keys("user_sessions:*")

    for user_key in user_session_keys:
        session_ids = await redis.smembers(user_key)
        for sid in session_ids:
            sid_str = sid.decode() if isinstance(sid, bytes) else sid
            session_key = f"stream_session:{sid_str}"
            exists = await redis.exists(session_key)
            if not exists:
                # Session expired, stop DeepStream pipeline and remove from user's set
                await notify_deepstream_stop(sid_str)
                await redis.srem(user_key, sid)
                cleaned += 1

        # If user has no more sessions, delete the key
        count = await redis.scard(user_key)
        if count == 0:
            await redis.delete(user_key)

    if cleaned > 0:
        logger.info(f"Cleaned up {cleaned} expired sessions")


async def startup_cleanup():
    """Run on startup to clean all stale sessions"""
    redis = await get_redis_pool()
    if not redis:
        return

    logger.info("Running startup session cleanup...")

    # Clean up expired sessions from user_sessions sets
    await cleanup_expired_sessions()

    # Also clean up any stream_session keys that are in "pending" status for too long
    session_keys = await redis.keys("stream_session:*")
    for session_key in session_keys:
        session_data = await redis.hgetall(session_key)
        if not session_data:
            continue
        status_val = session_data.get("status", "")
        created_at_str = session_data.get("created_at", "")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
                # Remove sessions older than 1 hour or stuck in "pending" for > 10 minutes
                if age_seconds > 3600 or (status_val == "pending" and age_seconds > 600):
                    sid = session_data.get("session_id", "")
                    user_id = session_data.get("user_id", "")

                    await notify_deepstream_stop(sid)
                    if user_id:
                        await redis.srem(f"user_sessions:{user_id}", sid)
                    await redis.delete(session_key)
                    logger.info(f"Startup cleanup: removed stale session {sid} (age={age_seconds:.0f}s, status={status_val})")
            except (ValueError, TypeError):
                pass

    logger.info("Startup session cleanup complete")


async def periodic_cleanup():
    """Run cleanup every 5 minutes"""
    while True:
        try:
            await cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(300)  # 5 minutes




def generate_class_colors(labels: list) -> dict:
    """Generate distinct colors for each unique label."""
    color_palette = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
        "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
        "#F8B500", "#82E0AA", "#F1948A", "#85929E", "#D7BDE2",
        "#A3E4D7",
    ]
    return {label: color_palette[i % len(color_palette)] for i, label in enumerate(labels)}


@router.post("/start", response_model=StreamSessionResponse)
async def start_stream_session(
    session_data: StreamSessionCreate,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Create a new streaming session"""
    # Verify model exists
    query = select(Model).where(Model.id == session_data.model_id)
    result = await db.execute(query)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )

    # Check access permission
    if not model.is_public and model.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to private model"
        )

    # Check user's active session count
    user_sessions_key = f"user_sessions:{current_user.id}"

    # Clean up expired sessions first
    session_ids = await redis.smembers(user_sessions_key)
    for sid in session_ids:
        session_key = f"stream_session:{sid}"
        exists = await redis.exists(session_key)
        if not exists:
            # Session expired, remove from user's set
            await redis.srem(user_sessions_key, sid)

    # Now check active count
    active_sessions = await redis.scard(user_sessions_key)
    if active_sessions >= 500:  # Max 5 concurrent sessions per user
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum concurrent sessions reached (500)"
        )

    # Create session
    session_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=1)

    # Generate stream URLs based on stream type
    # Use PUBLIC URLs for external access (user's browser/ffmpeg)
    stream_key = f"{session_id}"
    # RTMP push URL for user (OBS/FFmpeg pushes to SRS)
    stream_url = f"{settings.SRS_RTMP_PUBLIC_URL}/live/{stream_key}"
    # HLS playback URL (browser plays DeepStream-processed output via hls.js)
    playback_url = f"{settings.SRS_HLS_PUBLIC_URL}/output/{stream_key}.m3u8"

    # Get model class names and colors
    class_names = []
    class_colors = {}
    if model.class_config:
        class_names = [c["name"] for c in model.class_config]
        class_colors = {c["name"]: c["color"] for c in model.class_config}
    if not class_colors and class_names:
        class_colors = generate_class_colors(class_names)

    # Handle OWL-specific parameters
    owl_text_prompts_str = session_data.text_prompts or ""
    owl_variant = session_data.owl_variant or ""
    if owl_text_prompts_str:
        owl_prompts = [t.strip() for t in owl_text_prompts_str.split(",") if t.strip()]
        # For OWL, use text prompts as class names and auto-generate colors
        if owl_prompts and not class_names:
            class_names = owl_prompts
            class_colors = generate_class_colors(owl_prompts)

    # Store session in Redis
    session_key = f"stream_session:{session_id}"
    await redis.hset(
        session_key,
        mapping={
            "session_id": str(session_id),
            "model_id": str(session_data.model_id),
            "user_id": str(current_user.id),
            "stream_type": session_data.stream_type,
            "stream_key": stream_key,
            "stream_url": stream_url,
            "playback_url": playback_url,
            "status": "pending",
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "frames_processed": "0",
            "class_names": json.dumps(class_names),
            "class_colors": json.dumps(class_colors),
            "owl_text_prompts": owl_text_prompts_str,
            "owl_variant": owl_variant,
        }
    )
    await redis.expire(session_key, 3600)  # 1 hour TTL

    # Add to user's sessions (don't refresh TTL - let it expire naturally)
    await redis.sadd(user_sessions_key, str(session_id))

    return StreamSessionResponse(
        session_id=session_id,
        model_id=session_data.model_id,
        stream_url=stream_url,
        playback_url=playback_url,
        status="pending",
        created_at=created_at,
        expires_at=expires_at,
    )


@router.post("/{session_id}/activate")
async def activate_stream_session(
    session_id: uuid.UUID,
    conf_threshold: float = Query(0.25, ge=0.0, le=1.0),
    iou_threshold: float = Query(0.45, ge=0.0, le=1.0),
    text_prompts: Optional[str] = Query(None, description="Comma-separated text prompts for OWL open-vocabulary detection"),
    owl_variant: Optional[str] = Query(None, description="OWL model variant"),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Activate inference for a stream session (call after stream is published)"""
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )

    # Verify ownership
    if session_data.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )

    # Parse stored data
    model_id = session_data.get("model_id")
    stream_key = session_data.get("stream_key", str(session_id))
    class_names = json.loads(session_data.get("class_names", "[]"))
    class_colors = json.loads(session_data.get("class_colors", "{}"))

    # Resolve OWL parameters: request params override stored values
    if text_prompts and text_prompts.strip():
        owl_text_prompts_str = text_prompts.strip()
    else:
        owl_text_prompts_str = session_data.get("owl_text_prompts", "")

    effective_owl_variant = owl_variant or session_data.get("owl_variant", "") or "owlv2-base-patch16"

    owl_text_prompts = None
    if owl_text_prompts_str:
        owl_text_prompts = [t.strip() for t in owl_text_prompts_str.split(",") if t.strip()]
        # Update class names/colors based on new prompts
        if owl_text_prompts:
            class_names = owl_text_prompts
            class_colors = generate_class_colors(owl_text_prompts)

    # Persist updated prompts to Redis session
    if owl_text_prompts_str:
        await redis.hset(session_key, mapping={
            "owl_text_prompts": owl_text_prompts_str,
            "owl_variant": effective_owl_variant,
            "class_names": json.dumps(class_names),
            "class_colors": json.dumps(class_colors),
        })

    # Triton model name follows the convention: model_{model_id}
    triton_model_name = f"model_{model_id}"

    # Start DeepStream GPU pipeline via DeepStream service API
    model_type = "owl" if owl_text_prompts else "yolo"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{DEEPSTREAM_API_URL}/pipelines",
                json={
                    "session_id": str(session_id),
                    "model_type": model_type,
                    "model_name": triton_model_name,
                    "triton_url": None,  # use default from DeepStream env
                    "input_url": None,  # auto-derived from session_id
                    "class_names": class_names,
                    "class_colors": class_colors,
                    "conf_threshold": conf_threshold,
                    "iou_threshold": iou_threshold,
                    "owl_prompts": owl_text_prompts if owl_text_prompts else None,
                    "owl_variant": effective_owl_variant if owl_text_prompts else None,
                },
            )
            if resp.status_code not in (200, 201):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"DeepStream pipeline creation failed: {resp.text}",
                )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DeepStream service unavailable: {e}",
        )

    # Update session status
    await redis.hset(session_key, "status", "active")

    return {"status": "active", "session_id": str(session_id), "message": "Inference activated"}


@router.post("/{session_id}/update-prompts")
async def update_stream_prompts(
    session_id: uuid.UUID,
    text_prompts: str = Query(..., description="New comma-separated text prompts"),
    owl_variant: Optional[str] = Query(None, description="OWL model variant"),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Dynamically update OWL text prompts for an active stream session.
    Re-encodes text embeddings so the next inference frame uses the new prompts.
    """
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )

    if session_data.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )

    if session_data.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active. Activate inference first."
        )

    # Parse new prompts
    new_prompts = [t.strip() for t in text_prompts.split(",") if t.strip()]
    if not new_prompts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one text prompt is required"
        )

    effective_variant = owl_variant or session_data.get("owl_variant", "") or "owlv2-base-patch16"
    new_colors = generate_class_colors(new_prompts)

    # Update Redis session data
    await redis.hset(session_key, mapping={
        "owl_text_prompts": text_prompts.strip(),
        "owl_variant": effective_variant,
        "class_names": json.dumps(new_prompts),
        "class_colors": json.dumps(new_colors),
    })

    # Update the DeepStream pipeline with new prompts
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.patch(
                f"{DEEPSTREAM_API_URL}/pipelines/{session_id}",
                json={"owl_prompts": new_prompts},
            )
    except Exception as e:
        logger.warning(f"Could not update DeepStream pipeline prompts: {e}")

    return {
        "status": "updated",
        "session_id": str(session_id),
        "message": f"Text prompts updated to: {', '.join(new_prompts)}",
        "prompts": new_prompts,
    }


@router.get("/{session_id}/status", response_model=StreamStatusResponse)
async def get_stream_status(
    session_id: uuid.UUID,
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Get streaming session status and latest result"""
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )

    # Verify ownership
    if session_data.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )

    # Get pipeline stats from DeepStream service
    frames_processed = 0
    current_fps = 0.0
    avg_latency_ms = 0.0

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{DEEPSTREAM_API_URL}/pipelines/{session_id}/stats")
            if resp.status_code == 200:
                stats = resp.json()
                frames_processed = stats.get("frames_processed", 0)
                avg_latency_ms = stats.get("avg_latency_ms", 0)
                current_fps = 1000.0 / avg_latency_ms if avg_latency_ms > 0 else 0
    except Exception:
        pass

    return StreamStatusResponse(
        session_id=session_id,
        status=session_data.get("status", "unknown"),
        frames_processed=frames_processed,
        current_fps=current_fps,
        avg_latency_ms=avg_latency_ms,
        last_result=None,
    )


@router.get("/{session_id}/latest-result")
async def get_latest_result(
    session_id: uuid.UUID,
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Get the latest inference result for a session"""
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )

    # Verify ownership
    if session_data.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )

    # Read latest result from Redis (published by DeepStream metadata extractor)
    result_key = f"stream_result:{session_id}:latest"
    result_json = await redis.get(result_key)
    if not result_json:
        return {"status": "no_result", "message": "No inference results yet"}

    result = json.loads(result_json)

    return result


@router.post("/{session_id}/stop")
async def stop_stream_session(
    session_id: uuid.UUID,
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """Stop a streaming session"""
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired"
        )

    # Verify ownership
    if session_data.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )

    # Stop DeepStream pipeline
    await notify_deepstream_stop(str(session_id))

    # Update status and clean up
    await redis.hset(session_key, "status", "stopped")
    user_sessions_key = f"user_sessions:{current_user.id}"
    await redis.srem(user_sessions_key, str(session_id))
    await redis.delete(session_key)

    # Clean up related Redis keys
    await redis.delete(f"stream_result:{session_id}:latest")

    return {"status": "stopped", "session_id": str(session_id)}


@router.post("/{session_id}/beacon-stop")
async def beacon_stop_stream_session(
    session_id: uuid.UUID,
    redis=Depends(get_redis),
):
    """Stop a streaming session via sendBeacon (no auth required, uses session_id as token)"""
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        return {"status": "not_found"}

    # Stop DeepStream pipeline
    await notify_deepstream_stop(str(session_id))

    # Clean up
    user_id = session_data.get("user_id")
    if user_id:
        user_sessions_key = f"user_sessions:{user_id}"
        await redis.srem(user_sessions_key, str(session_id))
    await redis.delete(session_key)

    # Clean up related Redis keys
    await redis.delete(f"stream_result:{session_id}:latest")

    return {"status": "stopped", "session_id": str(session_id)}


# ============= WebSocket Endpoints =============

@router.websocket("/{session_id}/ws")
async def websocket_stream_results(
    websocket: WebSocket,
    session_id: uuid.UUID,
):
    """WebSocket endpoint for real-time inference results"""
    await websocket.accept()

    redis = await get_redis_pool()
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        await websocket.send_json({"error": "Session not found or expired"})
        await websocket.close()
        return

    # Subscribe to Redis channel for real-time results
    channel = f"stream_results:{session_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        # Send initial status
        await websocket.send_json({
            "type": "connected",
            "session_id": str(session_id),
            "status": session_data.get("status", "unknown"),
        })

        # Listen for messages
        while True:
            # Check for WebSocket messages (ping/pong, control messages)
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=0.1
                )

                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json({
                        "type": "inference_result",
                        **data
                    })

            except asyncio.TimeoutError:
                pass

            # Send heartbeat every 5 seconds
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.01
                )
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


@router.websocket("/{session_id}/ws/control")
async def websocket_stream_control(
    websocket: WebSocket,
    session_id: uuid.UUID,
):
    """WebSocket endpoint for controlling stream inference parameters"""
    await websocket.accept()

    redis = await get_redis_pool()
    session_key = f"stream_session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        await websocket.send_json({"error": "Session not found or expired"})
        await websocket.close()
        return

    try:
        await websocket.send_json({
            "type": "connected",
            "session_id": str(session_id),
        })

        while True:
            data = await websocket.receive_json()
            command = data.get("command")

            if command == "update_threshold":
                conf = data.get("conf_threshold", 0.25)
                iou = data.get("iou_threshold", 0.45)
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.patch(
                            f"{DEEPSTREAM_API_URL}/pipelines/{session_id}",
                            json={"conf_threshold": conf, "iou_threshold": iou},
                        )
                except Exception as e:
                    logger.warning(f"DeepStream threshold update failed: {e}")
                await websocket.send_json({
                    "type": "threshold_updated",
                    "conf_threshold": conf,
                    "iou_threshold": iou,
                })

            elif command == "update_prompts":
                raw_prompts = data.get("text_prompts", "")
                new_prompts = [t.strip() for t in raw_prompts.split(",") if t.strip()]
                if not new_prompts:
                    await websocket.send_json({
                        "type": "error",
                        "message": "At least one text prompt is required",
                    })
                else:
                    owl_variant = data.get("owl_variant", "owlv2-base-patch16")
                    new_colors = generate_class_colors(new_prompts)

                    # Update DeepStream pipeline
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            await client.patch(
                                f"{DEEPSTREAM_API_URL}/pipelines/{session_id}",
                                json={"owl_prompts": new_prompts},
                            )
                    except Exception as e:
                        logger.warning(f"DeepStream prompt update failed: {e}")

                    # Persist to Redis
                    await redis.hset(session_key, mapping={
                        "owl_text_prompts": raw_prompts.strip(),
                        "owl_variant": owl_variant,
                        "class_names": json.dumps(new_prompts),
                        "class_colors": json.dumps(new_colors),
                    })

                    logger.info(f"Updated OWL prompts via WS for session {session_id}: {new_prompts}")
                    await websocket.send_json({
                        "type": "prompts_updated",
                        "prompts": new_prompts,
                        "class_colors": new_colors,
                    })

            elif command == "get_stats":
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(f"{DEEPSTREAM_API_URL}/pipelines/{session_id}/stats")
                        if resp.status_code == 200:
                            stats = resp.json()
                            avg_latency = stats.get("avg_latency_ms", 0)
                            await websocket.send_json({
                                "type": "stats",
                                "frames_processed": stats.get("frames_processed", 0),
                                "avg_latency_ms": avg_latency,
                                "fps": 1000 / avg_latency if avg_latency > 0 else 0,
                            })
                except Exception:
                    pass

            elif command == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass

# Note: To enable periodic cleanup, add this to your FastAPI app startup:
# from app.api.v1.stream import periodic_cleanup
# asyncio.create_task(periodic_cleanup())
