"""FastAPI application entry point"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.redis import close_redis, init_redis
from app.core.minio import init_minio_buckets
from app.core.triton_repository import triton_repository
import asyncio
from app.api.v1.stream import periodic_cleanup, startup_cleanup
from app.core.owl_inference import owl_inference_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    await init_db()
    await init_redis()
    init_minio_buckets()
    # Load all deployed models in Triton
    await triton_repository.load_all_deployed_models()
    # Initialize OWL inference service (deploy models + load tokenizer)
    try:
        await owl_inference_service.initialize()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"OWL service initialization skipped: {e}")
    # Clean up stale sessions from previous run
    await startup_cleanup()
    # Start background cleanup task for stream sessions
    cleanup_task = asyncio.create_task(periodic_cleanup())
    yield
    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await close_db()
    await close_redis()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    app = FastAPI(
        title=settings.APP_NAME,
        description="实时交互式模型广场平台 - Real-time Interactive Model Square Platform",
        version=settings.APP_VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Include API routes
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": f"{settings.API_V1_PREFIX}/docs",
        }

    return app


app = create_app()
