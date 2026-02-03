"""Health check endpoints"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.gpu_manager import gpu_manager
from app.core.triton_repository import triton_repository
from app.models.model import Model
from app.models.user import User
from app.api.v1.auth import get_current_user

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


@router.get("/gpus")
async def gpu_status():
    """
    Get GPU status for all available GPUs.
    Returns memory usage, utilization, and load scores.
    """
    return gpu_manager.get_gpus_status_summary()


@router.get("/gpus/monitor")
async def gpu_monitor(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive GPU monitoring data including model distribution.
    Superuser only.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级用户可访问 GPU 监控"
        )
    
    # Get GPU status
    gpu_status = gpu_manager.get_gpus_status_summary()
    
    # Get all models from database
    result = await db.execute(
        select(Model).order_by(Model.created_at.desc())
    )
    models = result.scalars().all()
    
    # Build model info with GPU assignment
    models_info = []
    gpu_models_map = {}  # gpu_id -> list of models
    
    for model in models:
        model_id = str(model.id)
        gpu_id = triton_repository.get_model_gpu_id(model_id)
        is_deployed = triton_repository.is_model_deployed(model_id)
        is_loaded = triton_repository.is_model_ready(model_id)
        
        model_info = {
            "id": model_id,
            "name": model.name,
            "task_type": model.task_type.value if model.task_type else None,
            "network_type": model.network_type.value if model.network_type else None,
            "gpu_id": gpu_id,
            "is_deployed": is_deployed,
            "is_loaded": is_loaded,
            "created_at": model.created_at.isoformat() if model.created_at else None,
        }
        models_info.append(model_info)
        
        # Group by GPU
        if gpu_id is not None:
            if gpu_id not in gpu_models_map:
                gpu_models_map[gpu_id] = []
            gpu_models_map[gpu_id].append(model_info)
    
    # Enhance GPU info with models
    gpus_with_models = []
    for gpu in gpu_status.get("gpus", []):
        gpu_id = gpu["index"]
        gpu_info = {
            **gpu,
            "models": gpu_models_map.get(gpu_id, []),
            "model_count": len(gpu_models_map.get(gpu_id, [])),
        }
        gpus_with_models.append(gpu_info)
    
    return {
        "gpu_count": gpu_status.get("gpu_count", 0),
        "monitoring_available": gpu_status.get("monitoring_available", False),
        "gpus": gpus_with_models,
        "total_models": len(models_info),
        "deployed_models": sum(1 for m in models_info if m["is_deployed"]),
        "loaded_models": sum(1 for m in models_info if m["is_loaded"]),
        "unassigned_models": [m for m in models_info if m["gpu_id"] is None and m["is_deployed"]],
    }
