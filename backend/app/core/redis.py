"""Redis connection management"""

from typing import Optional

import redis.asyncio as redis

from app.core.config import settings

# Redis connection pool (decode_responses=True for general use)
redis_pool: Optional[redis.ConnectionPool] = None
redis_client: Optional[redis.Redis] = None

# Raw bytes Redis connection pool (decode_responses=False)
# Required for reading binary data from Redis Streams (e.g. raw video frames
# written by the FFmpeg worker).  The default pool uses decode_responses=True,
# which raises UnicodeDecodeError on non-UTF-8 binary payloads.
redis_pool_raw: Optional[redis.ConnectionPool] = None
redis_client_raw: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection pools"""
    global redis_pool, redis_client, redis_pool_raw, redis_client_raw
    redis_pool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )
    redis_client = redis.Redis(connection_pool=redis_pool)

    # Raw pool for binary stream operations (frame data)
    redis_pool_raw = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=10,
        decode_responses=False,
    )
    redis_client_raw = redis.Redis(connection_pool=redis_pool_raw)


async def close_redis():
    """Close Redis connections"""
    global redis_client, redis_pool, redis_client_raw, redis_pool_raw
    if redis_client:
        await redis_client.close()
    if redis_pool:
        await redis_pool.disconnect()
    if redis_client_raw:
        await redis_client_raw.close()
    if redis_pool_raw:
        await redis_pool_raw.disconnect()


async def get_redis() -> redis.Redis:
    """Dependency to get Redis client"""
    if redis_client is None:
        await init_redis()
    return redis_client


async def get_redis_pool() -> redis.Redis:
    """Get Redis client (alias for get_redis for compatibility)"""
    return await get_redis()


async def get_redis_raw() -> redis.Redis:
    """Get raw bytes Redis client (for binary stream data).

    This client does NOT decode responses, so all keys and values in
    returned dicts are ``bytes``.  Use this when reading Redis Streams
    that contain raw binary payloads (e.g. video frames).
    """
    if redis_client_raw is None:
        await init_redis()
    return redis_client_raw
