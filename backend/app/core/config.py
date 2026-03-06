"""Application configuration settings"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "ModelSquare"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/modelsquare"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 10

    # JWT Authentication
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:3010"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # MinIO / Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_PUBLIC_ENDPOINT: str = "localhost:9000"  # External URL for browser access
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_MODELS: str = "models"
    MINIO_BUCKET_THUMBNAILS: str = "thumbnails"
    MINIO_BUCKET_TEMP: str = "temp"

    # Triton Inference Server
    TRITON_URL: str = "localhost:8001"
    TRITON_MODEL_REPOSITORY: str = "/mnt/14TB/yangwen/code/AIcoder/ModelSquare/models"

    # vLLM Multimodal LLM Server
    VLLM_URL: str = "http://localhost:8100"
    VLLM_MODEL_NAME: str = "qwen3-vl"
    VLLM_TIMEOUT: int = 120  # seconds

    # SRS Streaming Server (internal for containers)
    SRS_RTMP_URL: str = "rtmp://localhost:1935/live"
    SRS_HTTP_URL: str = "http://localhost:8080"
    # SRS Public URLs (for external access from browser/ffmpeg)
    SRS_RTMP_PUBLIC_URL: str = "rtmp://localhost:1945/live"
    SRS_HTTP_PUBLIC_URL: str = "http://localhost:8090"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # Email Configuration
    SMTP_HOST: str = "smtp.qq.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "ModelSquare"
    SMTP_USE_TLS: bool = True

    # Email Verification
    EMAIL_CODE_EXPIRE_MINUTES: int = 10
    SUPERUSER_EMAIL_DOMAIN: str = "jouav.com"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
