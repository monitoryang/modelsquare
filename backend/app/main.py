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
import os

from app.api.v1.stream import periodic_cleanup, startup_cleanup
from app.core.owl_inference import owl_inference_service
from app.core.gpu_array import warmup as gpu_warmup


async def periodic_chunked_upload_cleanup():
    """Clean up expired chunked upload directories every hour."""
    import glob
    import time
    import logging
    logger = logging.getLogger(__name__)
    while True:
        try:
            await asyncio.sleep(3600)  # every hour
            import tempfile
            pattern = os.path.join(tempfile.gettempdir(), "chunked_upload_*")
            for dir_path in glob.glob(pattern):
                if not os.path.isdir(dir_path):
                    continue
                mtime = os.path.getmtime(dir_path)
                age_hours = (time.time() - mtime) / 3600
                if age_hours > 24:
                    import shutil
                    shutil.rmtree(dir_path, ignore_errors=True)
                    logger.info(f"Cleaned up expired upload dir: {dir_path}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Chunked upload cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    await init_db()
    await init_redis()
    init_minio_buckets()
    # Warm up CuPy GPU kernels (avoids JIT latency on first inference)
    gpu_warmup()
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
    # Start background cleanup tasks
    cleanup_task = asyncio.create_task(periodic_cleanup())
    upload_cleanup_task = asyncio.create_task(periodic_chunked_upload_cleanup())
    yield
    # Shutdown
    cleanup_task.cancel()
    upload_cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await upload_cleanup_task
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
