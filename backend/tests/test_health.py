import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import create_app


def test_health_endpoint():
    """Test basic health check endpoint"""
    app = create_app()
    client = TestClient(app)
    
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "modelsquare-api"


def test_database_health_endpoint_exists():
    """Test database health check endpoint exists"""
    app = create_app()
    client = TestClient(app)
    
    response = client.get("/api/v1/health/db")
    # The response could be 200 (if db is accessible) or 500 (if not)
    # but the endpoint should exist
    assert response.status_code in [200, 500]


def test_redis_health_endpoint_exists():
    """Test redis health check endpoint exists"""
    app = create_app()
    client = TestClient(app)
    
    response = client.get("/api/v1/health/redis")
    # The response could be 200 (if redis is accessible) or 500 (if not)
    assert response.status_code in [200, 500]


def test_readiness_endpoint_exists():
    """Test full readiness check endpoint exists"""
    app = create_app()
    client = TestClient(app)
    
    response = client.get("/api/v1/health/ready")
    # The response depends on whether external services are available
    assert response.status_code in [200, 500]
