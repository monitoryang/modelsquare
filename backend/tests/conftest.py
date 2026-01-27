import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.core.redis import get_redis
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app()
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    """Create async test client for FastAPI"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# Mock database session for testing
@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.close = MagicMock()
    return session


# Mock redis client for testing
@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.set = AsyncMock()
    redis.get = AsyncMock()
    return redis