import os
import pytest
from app.core.config import Settings, get_settings


def test_settings_default_values():
    """Test that default settings values are correctly set"""
    settings = Settings()
    
    assert settings.APP_NAME == "ModelSquare"
    assert settings.APP_VERSION == "1.0.0"
    assert settings.DATABASE_URL == "postgresql+asyncpg://postgres:postgres@localhost:5432/modelsquare"
    assert settings.REDIS_URL == "redis://localhost:6379/0"
    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 8000


def test_settings_from_env_vars():
    """Test that settings can be overridden by environment variables"""
    # Temporarily set environment variables
    original_app_name = os.environ.get('APP_NAME')
    os.environ['APP_NAME'] = 'TestApp'
    
    try:
        settings = Settings()
        assert settings.APP_NAME == 'TestApp'
    finally:
        # Restore original value
        if original_app_name is not None:
            os.environ['APP_NAME'] = original_app_name
        elif 'APP_NAME' in os.environ:
            del os.environ['APP_NAME']


def test_get_settings_cached():
    """Test that get_settings returns cached instance"""
    settings1 = get_settings()
    settings2 = get_settings()
    
    assert settings1 is settings2


def test_cors_settings():
    """Test CORS configuration settings"""
    settings = Settings()
    
    assert "http://localhost:5173" in settings.CORS_ORIGINS
    assert "http://localhost:3000" in settings.CORS_ORIGINS
    assert settings.CORS_ALLOW_CREDENTIALS is True
    assert settings.CORS_ALLOW_METHODS == ["*"]
    assert settings.CORS_ALLOW_HEADERS == ["*"]