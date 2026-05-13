"""Health check endpoints"""

import os
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import get_db
from app.core.minio import get_minio_client
from app.core.redis import get_redis
from app.core.gpu_manager import gpu_manager
from app.core.triton_repository import triton_repository, OWL_MODEL_VARIANTS
from app.models.model import Model, NetworkType
from app.models.user import User
from app.api.v1.auth import get_current_user

router = APIRouter()

# Storage monitoring cache
_storage_cache: dict = {"data": None, "timestamp": 0.0}
_STORAGE_CACHE_TTL = 60  # seconds


def _format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.2f} MB"
    elif size_bytes < 1024 ** 4:
        return f"{size_bytes / 1024 ** 3:.2f} GB"
    else:
        return f"{size_bytes / 1024 ** 4:.2f} TB"


def _get_mount_point(path: str) -> str:
    """Find the mount point of a given path."""
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def _get_local_disk_stats(paths: list[str]) -> list[dict]:
    """Get disk usage stats for given paths, deduplicated by mount point."""
    mount_map: dict[str, list[str]] = {}
    for p in paths:
        try:
            real_path = os.path.realpath(p)
            if not os.path.exists(real_path):
                continue
            mp = _get_mount_point(real_path)
            if mp not in mount_map:
                mount_map[mp] = []
            mount_map[mp].append(p)
        except Exception:
            continue

    disks = []
    for mount_point, monitored_paths in mount_map.items():
        try:
            usage = shutil.disk_usage(mount_point)
            usage_percent = round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0.0
            disks.append({
                "mount_point": mount_point,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "usage_percent": usage_percent,
                "total_display": _format_size(usage.total),
                "used_display": _format_size(usage.used),
                "free_display": _format_size(usage.free),
                "monitored_paths": monitored_paths,
            })
        except Exception:
            continue
    return disks


def _get_minio_bucket_stats(bucket_names: list[str]) -> dict:
    """Get MinIO bucket usage statistics."""
    try:
        client = get_minio_client()
        # Quick connectivity check
        client.list_buckets()
    except Exception:
        return {
            "available": False,
            "buckets": [],
            "total_used_bytes": 0,
            "total_used_display": "0 B",
            "total_object_count": 0,
        }

    buckets = []
    total_used = 0
    total_count = 0

    for bucket_name in bucket_names:
        try:
            obj_count = 0
            used_bytes = 0
            for obj in client.list_objects(bucket_name, recursive=True):
                if obj.size is not None:
                    used_bytes += obj.size
                obj_count += 1
            buckets.append({
                "name": bucket_name,
                "object_count": obj_count,
                "used_bytes": used_bytes,
                "used_display": _format_size(used_bytes),
            })
            total_used += used_bytes
            total_count += obj_count
        except Exception:
            buckets.append({
                "name": bucket_name,
                "object_count": 0,
                "used_bytes": 0,
                "used_display": "0 B",
            })

    return {
        "available": True,
        "buckets": buckets,
        "total_used_bytes": total_used,
        "total_used_display": _format_size(total_used),
        "total_object_count": total_count,
    }


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
        nt = model.network_type.value if model.network_type else ""
        is_deployed = triton_repository.is_model_deployed(model_id, network_type=nt)
        is_loaded = triton_repository.is_model_ready(model_id, network_type=nt)
        
        # OWL models use fixed Triton names — collect all unique GPU IDs
        owl_gpu_ids: list[int] = []
        if model.network_type == NetworkType.OWLv2:
            for vc in OWL_MODEL_VARIANTS.values():
                for triton_name in (vc["text_encoder_triton_name"], vc["image_encoder_triton_name"]):
                    gid = triton_repository.get_model_gpu_id_by_triton_name(triton_name)
                    if gid is not None and gid not in owl_gpu_ids:
                        owl_gpu_ids.append(gid)
            gpu_id = owl_gpu_ids[0] if owl_gpu_ids else None
        else:
            gpu_id = triton_repository.get_model_gpu_id(model_id)
        
        model_info = {
            "id": model_id,
            "name": model.name,
            "task_type": model.task_type.value if model.task_type else None,
            "network_type": nt,
            "gpu_id": gpu_id,
            "gpu_ids": owl_gpu_ids if owl_gpu_ids else ([gpu_id] if gpu_id is not None else []),
            "is_deployed": is_deployed,
            "is_loaded": is_loaded,
            "created_at": model.created_at.isoformat() if model.created_at else None,
        }
        models_info.append(model_info)
        
        # Group by GPU — OWL models may span multiple GPUs
        assigned_gpu_ids = owl_gpu_ids if owl_gpu_ids else ([gpu_id] if gpu_id is not None else [])
        for gid in assigned_gpu_ids:
            if gid not in gpu_models_map:
                gpu_models_map[gid] = []
            gpu_models_map[gid].append(model_info)
    
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


@router.get("/storage")
async def storage_monitor(
    current_user: User = Depends(get_current_user),
):
    """
    Get storage monitoring data including local disk and MinIO usage.
    Superuser only.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级用户可访问存储监控"
        )

    now = time.time()
    if _storage_cache["data"] and (now - _storage_cache["timestamp"]) < _STORAGE_CACHE_TTL:
        return _storage_cache["data"]

    local_disks = _get_local_disk_stats([
        settings.SHARED_VOLUME_PATH,
        settings.TRITON_MODEL_REPOSITORY,
    ])

    minio_stats = _get_minio_bucket_stats([
        settings.MINIO_BUCKET_MODELS,
        settings.MINIO_BUCKET_THUMBNAILS,
        settings.MINIO_BUCKET_TEMP,
        settings.MINIO_BUCKET_HLS,
    ])

    result = {"local_disks": local_disks, "minio": minio_stats}
    _storage_cache["data"] = result
    _storage_cache["timestamp"] = now
    return result
