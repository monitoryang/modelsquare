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
    import json
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

    # Set thumbnails bucket to public read
    thumbnails_bucket = settings.MINIO_BUCKET_THUMBNAILS
    public_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{thumbnails_bucket}/*"],
            }
        ],
    })
    try:
        client.set_bucket_policy(thumbnails_bucket, public_policy)
        print(f"Set public read policy on bucket: {thumbnails_bucket}")
    except S3Error as e:
        print(f"Error setting bucket policy for {thumbnails_bucket}: {e}")


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


async def download_file_to_path(
    bucket: str, object_name: str, dest_path: str, chunk_size: int = 1024 * 1024
) -> None:
    """
    Stream-download a file from MinIO directly to a local file path.

    Unlike ``download_file`` this never loads the entire object into memory,
    making it safe for large files (e.g. videos).
    """
    client = get_minio_client()

    try:
        response = client.get_object(bucket, object_name)
        try:
            with open(dest_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
        finally:
            response.close()
            response.release_conn()
    except S3Error as e:
        raise Exception(f"Failed to download file from MinIO: {e}")


def stream_file(bucket: str, object_name: str, chunk_size: int = 1024 * 1024):
    """
    Stream a file from MinIO in chunks (generator function)
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        chunk_size: Size of each chunk in bytes (default 1MB)
        
    Yields:
        File chunks as bytes
    """
    client = get_minio_client()
    
    try:
        response = client.get_object(bucket, object_name)
        try:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            response.close()
            response.release_conn()
    except S3Error as e:
        raise Exception(f"Failed to stream file from MinIO: {e}")


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
        Presigned URL string (with public endpoint for browser access)
    """
    from datetime import timedelta
    
    client = get_minio_client()
    
    try:
        url = client.presigned_get_object(
            bucket,
            object_name,
            expires=timedelta(hours=expires_hours),
        )
        # Replace internal endpoint with public endpoint for browser access
        if settings.MINIO_PUBLIC_ENDPOINT and settings.MINIO_PUBLIC_ENDPOINT != settings.MINIO_ENDPOINT:
            url = url.replace(settings.MINIO_ENDPOINT, settings.MINIO_PUBLIC_ENDPOINT)
        return url
    except S3Error as e:
        raise Exception(f"Failed to generate presigned URL: {e}")


def get_public_url(bucket: str, object_name: str) -> str:
    """
    Get a public URL for accessing a file (for public buckets like thumbnails)
    
    Args:
        bucket: Bucket name
        object_name: Object path in bucket
        
    Returns:
        Public URL string
    """
    endpoint = settings.MINIO_PUBLIC_ENDPOINT or settings.MINIO_ENDPOINT
    protocol = "https" if settings.MINIO_SECURE else "http"
    return f"{protocol}://{endpoint}/{bucket}/{object_name}"


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
