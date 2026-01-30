"""MinIO object storage client"""

import io
from typing import BinaryIO, Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

# Global MinIO client instance
minio_client: Optional[Minio] = None


def get_minio_client() -> Minio:
    """Get or create MinIO client instance"""
    global minio_client
    if minio_client is None:
        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return minio_client


def init_minio_buckets() -> None:
    """Initialize required MinIO buckets"""
    client = get_minio_client()
    buckets = [settings.MINIO_BUCKET_MODELS, settings.MINIO_BUCKET_THUMBNAILS, settings.MINIO_BUCKET_TEMP]
    
    for bucket in buckets:
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                print(f"Created MinIO bucket: {bucket}")
            else:
                print(f"MinIO bucket already exists: {bucket}")
        except S3Error as e:
            print(f"Error creating bucket {bucket}: {e}")


async def upload_file(
    bucket: str,
    object_name: str,
    file_data: BinaryIO,
    file_size: int,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Upload a file to MinIO
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        file_data: File binary data
        file_size: Size of file in bytes
        content_type: MIME type of file
        
    Returns:
        Object path in MinIO
    """
    client = get_minio_client()
    
    try:
        client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=file_data,
            length=file_size,
            content_type=content_type,
        )
        return f"{bucket}/{object_name}"
    except S3Error as e:
        raise Exception(f"Failed to upload file to MinIO: {e}")


async def download_file(bucket: str, object_name: str) -> bytes:
    """
    Download a file from MinIO
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        
    Returns:
        File bytes
    """
    client = get_minio_client()
    
    try:
        response = client.get_object(bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except S3Error as e:
        raise Exception(f"Failed to download file from MinIO: {e}")


async def delete_file(bucket: str, object_name: str) -> bool:
    """
    Delete a file from MinIO
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        
    Returns:
        True if deleted successfully
    """
    client = get_minio_client()
    
    try:
        client.remove_object(bucket, object_name)
        return True
    except S3Error as e:
        raise Exception(f"Failed to delete file from MinIO: {e}")


def get_presigned_url(
    bucket: str,
    object_name: str,
    expires_hours: int = 24,
) -> str:
    """
    Get a presigned URL for downloading a file
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        expires_hours: URL expiration time in hours
        
    Returns:
        Presigned URL string
    """
    from datetime import timedelta
    
    client = get_minio_client()
    
    try:
        url = client.presigned_get_object(
            bucket,
            object_name,
            expires=timedelta(hours=expires_hours),
        )
        return url
    except S3Error as e:
        raise Exception(f"Failed to generate presigned URL: {e}")


async def get_file_size(bucket: str, object_name: str) -> int:
    """
    Get the size of a file in MinIO
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        
    Returns:
        File size in bytes
    """
    client = get_minio_client()
    
    try:
        stat = client.stat_object(bucket, object_name)
        return stat.size
    except S3Error as e:
        raise Exception(f"Failed to get file stats from MinIO: {e}")
