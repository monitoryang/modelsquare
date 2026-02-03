"""API v1 router configuration"""

from fastapi import APIRouter

from app.api.v1 import auth, models, inference, stream, health, openapi

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(inference.router, prefix="/models", tags=["inference"])
api_router.include_router(stream.router, prefix="/stream", tags=["stream"])
api_router.include_router(openapi.router, prefix="/openapi", tags=["openapi"])
