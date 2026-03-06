"""FFmpeg Frame Extraction Worker

This worker receives streaming hooks from SRS and extracts frames
for inference processing. Frames are pushed to Redis Stream for
consumption by the inference service.
"""

import asyncio
import os
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Dict, Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SRS_RTMP_URL = os.getenv("SRS_RTMP_URL", "rtmp://localhost:1935/live")
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
FRAME_FPS = int(os.getenv("FRAME_FPS", "10"))

# Active stream processes
active_streams: Dict[str, subprocess.Popen] = {}
stream_tasks: Dict[str, asyncio.Task] = {}

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=False)
    print(f"[FFmpeg Worker] Connected to Redis at {REDIS_URL}")
    yield
    # Cleanup on shutdown
    for stream_key in list(active_streams.keys()):
        await stop_frame_extraction(stream_key)
    if redis_client:
        await redis_client.close()


app = FastAPI(title="FFmpeg Frame Extraction Worker", lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_streams": len(active_streams),
        "streams": list(active_streams.keys()),
    }


@app.post("/api/hooks/on_publish")
async def on_publish(hook: StreamHook):
    """Handle stream publish event from SRS"""
    stream_key = hook.stream  # Use stream name directly as key
    
    print(f"[FFmpeg Worker] on_publish: app={hook.app}, stream={hook.stream}")

    if stream_key in active_streams:
        return {"code": 0, "message": "Stream already being processed"}

    # Start frame extraction in background
    task = asyncio.create_task(start_frame_extraction(stream_key, hook.stream))
    stream_tasks[stream_key] = task

    return {"code": 0, "message": "Frame extraction started"}


@app.post("/api/hooks/on_unpublish")
async def on_unpublish(hook: StreamHook):
    """Handle stream unpublish event from SRS"""
    stream_key = hook.stream

    print(f"[FFmpeg Worker] on_unpublish: app={hook.app}, stream={hook.stream}")
    
    await stop_frame_extraction(stream_key)

    return {"code": 0, "message": "Frame extraction stopped"}


@app.post("/api/streams/{stream_name}/start")
async def manual_start_stream(stream_name: str):
    """Manually start frame extraction for a stream"""
    if stream_name in active_streams:
        return {"code": 0, "message": "Stream already being processed"}
    
    task = asyncio.create_task(start_frame_extraction(stream_name, stream_name))
    stream_tasks[stream_name] = task
    
    return {"code": 0, "message": "Frame extraction started"}


@app.post("/api/streams/{stream_name}/stop")
async def manual_stop_stream(stream_name: str):
    """Manually stop frame extraction for a stream"""
    await stop_frame_extraction(stream_name)
    return {"code": 0, "message": "Frame extraction stopped"}


@app.get("/api/streams")
async def list_streams():
    """List all active streams"""
    return {
        "streams": list(active_streams.keys()),
        "count": len(active_streams),
    }


async def stop_frame_extraction(stream_key: str):
    """Stop frame extraction for a stream"""
    # Cancel the task
    if stream_key in stream_tasks:
        task = stream_tasks.pop(stream_key)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Terminate the process
    if stream_key in active_streams:
        process = active_streams.pop(stream_key)
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        except Exception as e:
            print(f"[FFmpeg Worker] Error stopping process for {stream_key}: {e}")

    # Notify stream ended
    if redis_client:
        channel = f"stream_status:{stream_key}"
        await redis_client.publish(channel, b"stopped")


async def start_frame_extraction(stream_key: str, stream_name: str):
    """Start FFmpeg process for frame extraction"""
    rtmp_url = f"{SRS_RTMP_URL}/{stream_name}"
    
    print(f"[FFmpeg Worker] Starting frame extraction from {rtmp_url}")

    # FFmpeg command to extract frames and output to stdout as raw RGB
    cmd = [
        "ffmpeg",
        "-i", rtmp_url,
        "-vf", f"fps={FRAME_FPS},scale={FRAME_WIDTH}:{FRAME_HEIGHT}",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-loglevel", "error",
        "-",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        active_streams[stream_key] = process
        
        # Notify stream started
        if redis_client:
            channel = f"stream_status:{stream_key}"
            await redis_client.publish(channel, b"started")

        # Read frames and push to Redis Stream
        frame_size = FRAME_WIDTH * FRAME_HEIGHT * 3  # RGB24
        frame_count = 0
        redis_stream_key = f"stream:{stream_key}"
        
        print(f"[FFmpeg Worker] Reading frames (size={frame_size} bytes each)")

        while stream_key in active_streams:
            # Read one frame
            frame_data = process.stdout.read(frame_size)
            
            if not frame_data:
                # Check if process ended
                if process.poll() is not None:
                    print(f"[FFmpeg Worker] Process ended for {stream_key}")
                    break
                continue
                
            if len(frame_data) < frame_size:
                print(f"[FFmpeg Worker] Incomplete frame for {stream_key}")
                break

            frame_count += 1
            timestamp_ms = int(time.time() * 1000)

            # Push frame to Redis Stream
            try:
                await redis_client.xadd(
                    redis_stream_key,
                    {
                        b"frame_id": str(frame_count).encode(),
                        b"timestamp_ms": str(timestamp_ms).encode(),
                        b"width": str(FRAME_WIDTH).encode(),
                        b"height": str(FRAME_HEIGHT).encode(),
                        b"data": frame_data.hex().encode(),
                    },
                    maxlen=50,  # Keep only last 50 frames (5 seconds at 10fps)
                )
                
                if frame_count % 100 == 0:
                    print(f"[FFmpeg Worker] Processed {frame_count} frames for {stream_key}")
                    
            except Exception as e:
                print(f"[FFmpeg Worker] Redis error for {stream_key}: {e}")
                await asyncio.sleep(0.1)

        # Check for FFmpeg errors
        if process.poll() is not None:
            stderr = process.stderr.read().decode()
            if stderr:
                print(f"[FFmpeg Worker] FFmpeg error for {stream_key}: {stderr}")

    except asyncio.CancelledError:
        print(f"[FFmpeg Worker] Task cancelled for {stream_key}")
        raise
    except Exception as e:
        print(f"[FFmpeg Worker] Error processing stream {stream_key}: {e}")
    finally:
        print(f"[FFmpeg Worker] Cleanup for {stream_key}, processed {frame_count} frames")
        if stream_key in active_streams:
            active_streams.pop(stream_key, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
