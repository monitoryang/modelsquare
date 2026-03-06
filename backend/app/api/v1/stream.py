"""Streaming session endpoints with WebSocket support for real-time inference"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis, get_redis_pool
from app.core.stream_inference import stream_inference_service
from app.models.model import Model
from app.models.user import User
from app.schemas.inference import (
    StreamSessionCreate,
    StreamSessionResponse,
    StreamStatusResponse,
)

router = APIRouter()


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
    if active_sessions >= 5:  # Max 5 concurrent sessions per user
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum concurrent sessions reached (5)"
        )

    # Create session
    session_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=1)

    # Generate stream URLs based on stream type
    # Use PUBLIC URLs for external access (user's browser/ffmpeg)
    stream_key = f"{session_id}"
    if session_data.stream_type == "rtmp":
        stream_url = f"{settings.SRS_RTMP_PUBLIC_URL}/{stream_key}"
        playback_url = f"{settings.SRS_HTTP_PUBLIC_URL}/live/{stream_key}.flv"
    elif session_data.stream_type == "hls":
        stream_url = f"{settings.SRS_RTMP_PUBLIC_URL}/{stream_key}"
        playback_url = f"{settings.SRS_HTTP_PUBLIC_URL}/live/{stream_key}.m3u8"
    else:  # webrtc
        stream_url = f"webrtc://{settings.SRS_HTTP_PUBLIC_URL.replace('http://', '')}/live/{stream_key}"
        playback_url = stream_url

    # Get model class names and colors
    class_names = []
    class_colors = {}
    if model.class_config:
        class_names = [c["name"] for c in model.class_config]
        class_colors = {c["name"]: c["color"] for c in model.class_config}
    if not class_colors and class_names:
        class_colors = generate_class_colors(class_names)

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
        }
    )
    await redis.expire(session_key, 3600)  # 1 hour TTL

    # Add to user's sessions
    await redis.sadd(user_sessions_key, str(session_id))
    await redis.expire(user_sessions_key, 3600)

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

    # Start inference session
    await stream_inference_service.start_session(
        session_id=str(session_id),
        model_id=model_id,
        stream_name=stream_key,
        class_names=class_names,
        class_colors=class_colors,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
    )

    # Update session status
    await redis.hset(session_key, "status", "active")

    return {"status": "active", "session_id": str(session_id), "message": "Inference activated"}


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

    # Get inference session stats
    inference_session = stream_inference_service.get_session(str(session_id))
    frames_processed = 0
    current_fps = 0.0
    avg_latency_ms = 0.0

    if inference_session:
        frames_processed = inference_session.frames_processed
        if frames_processed > 0:
            avg_latency_ms = inference_session.total_latency_ms / frames_processed
            # Estimate FPS based on latency
            current_fps = 1000.0 / avg_latency_ms if avg_latency_ms > 0 else 0

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

    result = await stream_inference_service.get_latest_result(str(session_id))
    
    if not result:
        return {"status": "no_result", "message": "No inference results yet"}
    
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

    # Stop inference session
    await stream_inference_service.stop_session(str(session_id))

    # Update status and clean up
    await redis.hset(session_key, "status", "stopped")
    user_sessions_key = f"user_sessions:{current_user.id}"
    await redis.srem(user_sessions_key, str(session_id))

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
                session = stream_inference_service.get_session(str(session_id))
                if session:
                    session.conf_threshold = data.get("conf_threshold", session.conf_threshold)
                    session.iou_threshold = data.get("iou_threshold", session.iou_threshold)
                    await websocket.send_json({
                        "type": "threshold_updated",
                        "conf_threshold": session.conf_threshold,
                        "iou_threshold": session.iou_threshold,
                    })
            
            elif command == "get_stats":
                session = stream_inference_service.get_session(str(session_id))
                if session:
                    avg_latency = session.total_latency_ms / session.frames_processed if session.frames_processed > 0 else 0
                    await websocket.send_json({
                        "type": "stats",
                        "frames_processed": session.frames_processed,
                        "avg_latency_ms": avg_latency,
                        "fps": 1000 / avg_latency if avg_latency > 0 else 0,
                    })
                    
            elif command == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
