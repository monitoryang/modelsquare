import pytest
from fastapi.testclient import TestClient
from app.main import app, create_app


def test_app_configuration():
    """Test that the app is configured with correct settings"""
    test_app = create_app()
    assert test_app.title == "ModelSquare"
    assert test_app.description == "实时交互式模型广场平台 - Real-time Interactive Model Square Platform"
    assert test_app.version == "1.0.0"


def test_root_endpoint():
    """Test the root endpoint returns correct data"""
    client = TestClient(app)
    
    response = client.get("/")
        
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ModelSquare"
    assert data["version"] == "1.0.0"
    assert "/api/v1/docs" in data["docs"]


def test_health_check():
    """Test the health check endpoint"""
    client = TestClient(app)
    
    response = client.get("/api/v1/health")
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "modelsquare-api"