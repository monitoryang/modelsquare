"""Streaming session endpoints"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.model import Model
from app.models.user import User
from app.schemas.inference import (
    StreamSessionCreate,
    StreamSessionResponse,
    StreamStatusResponse,
)

router = APIRouter()


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
    stream_key = f"{session_id}"
    if session_data.stream_type == "rtmp":
        stream_url = f"{settings.SRS_RTMP_URL}/{stream_key}"
        playback_url = f"{settings.SRS_HTTP_URL}/live/{stream_key}.flv"
    elif session_data.stream_type == "hls":
        stream_url = f"{settings.SRS_RTMP_URL}/{stream_key}"
        playback_url = f"{settings.SRS_HTTP_URL}/live/{stream_key}.m3u8"
    else:  # webrtc
        stream_url = f"webrtc://{settings.SRS_HTTP_URL}/live/{stream_key}"
        playback_url = stream_url

    # Store session in Redis
    session_key = f"stream_session:{session_id}"
    await redis.hset(
        session_key,
        mapping={
            "session_id": str(session_id),
            "model_id": str(session_data.model_id),
            "user_id": str(current_user.id),
            "stream_type": session_data.stream_type,
            "stream_url": stream_url,
            "playback_url": playback_url,
            "status": "pending",
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "frames_processed": "0",
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

    # Get latest inference result if available
    result_key = f"stream_result:{session_id}:latest"
    latest_result = await redis.hgetall(result_key)

    return StreamStatusResponse(
        session_id=session_id,
        status=session_data.get("status", "unknown"),
        frames_processed=int(session_data.get("frames_processed", 0)),
        current_fps=float(session_data.get("current_fps", 0)),
        avg_latency_ms=float(session_data.get("avg_latency_ms", 0)),
        last_result=None,  # TODO: Parse latest_result into InferenceResponse
    )


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

    # Update status and clean up
    await redis.hset(session_key, "status", "stopped")
    user_sessions_key = f"user_sessions:{current_user.id}"
    await redis.srem(user_sessions_key, str(session_id))

    return {"status": "stopped", "session_id": str(session_id)}
