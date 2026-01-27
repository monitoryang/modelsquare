import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from app.main import create_app
from app.core.database import get_db
from uuid import uuid4


# Mock database dependency that returns empty results
async def override_get_db():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    mock_result.scalar = MagicMock(return_value=0)
    
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.close = AsyncMock()
    yield mock_db


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_models(client):
    """Test listing all models"""
    response = client.get("/api/v1/models")
    
    # Should return 200 with empty list (mocked db returns empty)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_get_model_by_id(client):
    """Test retrieving a specific model by ID"""
    # Using a random UUID to test the endpoint
    random_uuid = str(uuid4())
    response = client.get(f"/api/v1/models/{random_uuid}")
        
    # Model not found in mock db
    assert response.status_code == 404


def test_create_model_requires_auth(client):
    """Test creating a new model requires authentication"""
    model_data = {
        "name": "test_model",
        "description": "A test model",
        "version": "1.0.0",
        "framework": "pytorch",
        "task_type": "classification",
        "is_public": True
    }
    
    response = client.post("/api/v1/models", json=model_data)
        
    # Should return 401 for missing auth
    assert response.status_code == 401


def test_update_model_requires_auth(client):
    """Test updating a model requires authentication"""
    update_data = {
        "name": "updated_model",
        "description": "Updated description",
        "version": "2.0.0"
    }
    
    random_uuid = str(uuid4())
    response = client.patch(f"/api/v1/models/{random_uuid}", json=update_data)
        
    # Should return 401 for missing auth
    assert response.status_code == 401


def test_delete_model_requires_auth(client):
    """Test deleting a model requires authentication"""
    random_uuid = str(uuid4())
    response = client.delete(f"/api/v1/models/{random_uuid}")
        
    # Should return 401 for missing auth
    assert response.status_code == 401
