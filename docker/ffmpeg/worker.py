"""FFmpeg Frame Extraction Worker

This worker receives streaming hooks from SRS and extracts frames
for inference processing.
"""

import asyncio
import os
import subprocess
from typing import Dict, Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="FFmpeg Frame Extraction Worker")

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SRS_RTMP_URL = os.getenv("SRS_RTMP_URL", "rtmp://localhost:1935/live")

# Active stream processes
active_streams: Dict[str, subprocess.Popen] = {}

# Redis client
redis_client: Optional[redis.Redis] = None


class StreamHook(BaseModel):
    """SRS stream hook payload"""
    action: str
    client_id: str
    ip: str
    vhost: str
    app: str
    stream: str
    tcUrl: Optional[str] = None
    pageUrl: Optional[str] = None


@app.on_event("startup")
async def startup():
    """Initialize Redis connection"""
    global redis_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    # Stop all active FFmpeg processes
    for stream_key, process in active_streams.items():
        process.terminate()
        process.wait()
    active_streams.clear()

    if redis_client:
        await redis_client.close()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "active_streams": len(active_streams)}


@app.post("/api/hooks/on_publish")
async def on_publish(hook: StreamHook):
    """Handle stream publish event from SRS"""
    stream_key = f"{hook.app}/{hook.stream}"

    if stream_key in active_streams:
        return {"code": 0, "message": "Stream already being processed"}

    # Start frame extraction in background
    asyncio.create_task(start_frame_extraction(stream_key, hook.stream))

    return {"code": 0, "message": "Frame extraction started"}


@app.post("/api/hooks/on_unpublish")
async def on_unpublish(hook: StreamHook):
    """Handle stream unpublish event from SRS"""
    stream_key = f"{hook.app}/{hook.stream}"

    if stream_key in active_streams:
        process = active_streams.pop(stream_key)
        process.terminate()
        process.wait()

    return {"code": 0, "message": "Frame extraction stopped"}


async def start_frame_extraction(stream_key: str, stream_name: str):
    """Start FFmpeg process for frame extraction"""
    rtmp_url = f"{SRS_RTMP_URL}/{stream_name}"

    # FFmpeg command to extract frames at 10 fps and output to stdout as raw RGB
    cmd = [
        "ffmpeg",
        "-i", rtmp_url,
        "-vf", "fps=10,scale=640:480",  # 10 fps, resize to 640x480
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        active_streams[stream_key] = process

        # Read frames and push to Redis Stream
        frame_size = 640 * 480 * 3  # RGB24
        frame_count = 0

        while stream_key in active_streams:
            frame_data = process.stdout.read(frame_size)
            if not frame_data or len(frame_data) < frame_size:
                break

            frame_count += 1

            # Push frame to Redis Stream
            await redis_client.xadd(
                f"stream:{stream_name}",
                {
                    "frame_id": str(frame_count),
                    "width": "640",
                    "height": "480",
                    "data": frame_data.hex(),  # Store as hex string
                },
                maxlen=100,  # Keep only last 100 frames
            )

    except Exception as e:
        print(f"Error processing stream {stream_key}: {e}")
    finally:
        if stream_key in active_streams:
            active_streams.pop(stream_key, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
