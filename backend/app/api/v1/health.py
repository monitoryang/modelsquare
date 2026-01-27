"""Health check endpoints"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter()


@router.get("")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "service": "modelsquare-api"}


@router.get("/db")
async def database_health(db: AsyncSession = Depends(get_db)):
    """Database connection health check"""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@router.get("/redis")
async def redis_health(redis=Depends(get_redis)):
    """Redis connection health check"""
    try:
        await redis.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "redis": "disconnected", "error": str(e)}


@router.get("/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis)
):
    """Full readiness check for all dependencies"""
    status = {"status": "healthy", "dependencies": {}}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        status["dependencies"]["database"] = "connected"
    except Exception:
        status["status"] = "unhealthy"
        status["dependencies"]["database"] = "disconnected"

    # Check Redis
    try:
        await redis.ping()
        status["dependencies"]["redis"] = "connected"
    except Exception:
        status["status"] = "unhealthy"
        status["dependencies"]["redis"] = "disconnected"

    return status
