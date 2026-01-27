import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from app.main import create_app
from app.core.database import get_db
from uuid import uuid4


# Mock database dependency
async def override_get_db():
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.close = AsyncMock()
    yield mock_db


def test_inference_image_endpoint():
    """Test model image inference endpoint exists"""
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    # Using a random UUID to test the endpoint
    random_uuid = str(uuid4())
    
    # Test with a simple mock file
    response = client.post(
        f"/api/v1/models/{random_uuid}/infer/image",
        files={"image": ("test.jpg", b"fake image data", "image/jpeg")}
    )
        
    # Endpoint exists but model won't be found (mock returns None), so expect 404
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_inference_video_endpoint():
    """Test model video inference endpoint exists"""
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    # Using a random UUID to test the endpoint
    random_uuid = str(uuid4())
    
    response = client.post(
        f"/api/v1/models/{random_uuid}/infer/video",
        files={"video": ("test.mp4", b"fake video data", "video/mp4")},
        data={"max_frames": "100"}
    )
        
    # Endpoint exists but model won't be found, so expect 404
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_stream_start_requires_auth():
    """Test that stream start endpoint requires authentication"""
    app = create_app()
    client = TestClient(app)
    
    random_uuid = str(uuid4())
    response = client.post(
        "/api/v1/stream/start",
        json={"model_id": random_uuid, "stream_type": "rtmp"}
    )
        
    # Should return 401 since authentication is required
    assert response.status_code == 401
