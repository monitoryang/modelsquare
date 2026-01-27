import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import create_app
from app.core.database import get_db
import jwt
from app.core.config import settings
from uuid import uuid4
from datetime import datetime, timezone


# Mock database dependency
async def override_get_db():
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.close = AsyncMock()
    
    # Mock refresh to populate the user object with realistic values
    async def mock_refresh(obj):
        obj.id = uuid4()
        obj.is_active = True
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)
    
    mock_db.refresh = mock_refresh
    yield mock_db


def test_login_form_fields():
    """Test that login endpoint accepts the right form fields"""
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    # Testing that the endpoint exists and requires proper form data
    response = client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "Test@123"
    })
    
    # Expect 401 for auth failure (user not found in mock db)
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_register_user():
    """Test user registration endpoint"""
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    # Testing that the endpoint exists and requires proper json data
    response = client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "username": "newuser",
        "full_name": "New User",
        "password": "Test@123"
    })
    
    # Should return 201 for success with mocked db
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    app.dependency_overrides.clear()


def test_get_current_user():
    """Test getting current user info with valid token"""
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    # Create a fake token
    fake_payload = {"sub": "test-uuid", "email": "test@example.com", "exp": 9999999999}
    fake_token = jwt.encode(fake_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    # Access protected endpoint with token
    response = client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {fake_token}"
    })
    
    # With mock db returning None, expect 401
    assert response.status_code == 401
    app.dependency_overrides.clear()
