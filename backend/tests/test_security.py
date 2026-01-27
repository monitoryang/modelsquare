import pytest
from datetime import datetime, timedelta, timezone
from jose import JWTError

from app.core.security import (
    create_access_token, 
    create_refresh_token, 
    decode_token, 
    get_password_hash, 
    verify_password,
    TokenData
)
from app.core.config import settings


def test_password_hashing():
    """Test password hashing and verification"""
    # Using a short password to avoid bcrypt length limit (72 bytes)
    plain_password = "Test@123"
    hashed_password = get_password_hash(plain_password)
    
    # Verify the password
    assert verify_password(plain_password, hashed_password) is True
    assert verify_password("wrongpwd", hashed_password) is False


def test_create_and_decode_access_token():
    """Test creating and decoding access tokens"""
    data = {"sub": "testuser", "email": "test@example.com"}
    token = create_access_token(data)
    
    # Decode and verify the token
    decoded_data = decode_token(token)
    assert decoded_data.user_id == "testuser"
    assert decoded_data.email == "test@example.com"


def test_create_refresh_token():
    """Test creating refresh tokens"""
    data = {"sub": "testuser", "email": "test@example.com"}
    token = create_refresh_token(data)
    
    # Decode the token to check if it's valid
    decoded_data = decode_token(token)
    assert decoded_data.user_id == "testuser"
    assert decoded_data.email == "test@example.com"


def test_token_expiration():
    """Test that tokens expire correctly"""
    # Create a token that expires in the past
    expired_data = {"sub": "testuser", "email": "test@example.com"}
    expired_token = create_access_token({
        "sub": "testuser", 
        "email": "test@example.com"
    }, timedelta(seconds=-1))  # Expired 1 second ago
    
    # Try to decode the expired token - should return None
    decoded_data = decode_token(expired_token)
    assert decoded_data is None


def test_invalid_token():
    """Test handling of invalid tokens"""
    # Test with a malformed token
    decoded_data = decode_token("invalid.token.here")
    assert decoded_data is None