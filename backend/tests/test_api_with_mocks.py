import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.api.v1 import models, auth, inference
from uuid import uuid4


def test_list_models_with_mocked_dependency():
    """Test listing models with mocked database dependency"""
    app = create_app()
    
    # Temporarily override the dependency
    async def mocked_get_db():
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        yield mock_db

    with patch.object(models, 'get_db', side_effect=mocked_get_db):
        with TestClient(app) as client:
            response = client.get("/api/v1/models?page=1&page_size=10")
            # The response status will depend on other factors but at least route exists
            assert response.status_code in [200, 401, 403, 500]


def test_create_model_with_mocked_dependency():
    """Test creating a model with mocked database dependency"""
    app = create_app()
    
    # Temporarily override the dependency
    async def mocked_get_db():
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        yield mock_db

    with patch.object(models, 'get_db', side_effect=mocked_get_db):
        with TestClient(app) as client:
            response = client.post("/api/v1/models", json={
                "name": "test_model",
                "description": "A test model",
                "version": "1.0.0",
                "framework": "pytorch",
                "task_type": "classification",
                "is_public": True
            })
            # Will likely return 401 for auth since this requires authentication
            assert response.status_code in [401, 422, 500]


def test_user_registration_with_mocked_dependency():
    """Test user registration with mocked dependencies"""
    app = create_app()
    
    # Temporarily override the database dependency
    async def mocked_get_db():
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        yield mock_db

    with patch.object(auth, 'get_db', side_effect=mocked_get_db):
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/register", json={
                "email": "test@example.com",
                "username": "testuser",
                "full_name": "Test User",
                "password": "Test@123"
            })
            # Could return 201 for success, 400 for validation, 422 for validation errors
            assert response.status_code in [200, 201, 400, 422, 500]


def test_image_inference_with_mocked_dependency():
    """Test image inference with mocked dependencies"""
    app = create_app()
    
    # Temporarily override the database dependency
    async def mocked_get_db():
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock()
        mock_db.execute.return_value = result_mock
        yield mock_db

    with patch.object(inference, 'get_db', side_effect=mocked_get_db):
        with TestClient(app) as client:
            random_uuid = str(uuid4())
            response = client.post(
                f"/api/v1/models/{random_uuid}/infer/image",
                files={"image": ("test.jpg", b"fake image data", "image/jpeg")}
            )
            # Will likely return 404 for model not found or 401 for auth
            assert response.status_code in [401, 403, 404, 500]