"""Redis connection management"""

from typing import Optional

import redis.asyncio as redis

from app.core.config import settings

# Redis connection pool
redis_pool: Optional[redis.ConnectionPool] = None
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection pool"""
    global redis_pool, redis_client
    redis_pool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )
    redis_client = redis.Redis(connection_pool=redis_pool)


async def close_redis():
    """Close Redis connections"""
    global redis_client, redis_pool
    if redis_client:
        await redis_client.close()
    if redis_pool:
        await redis_pool.disconnect()


async def get_redis() -> redis.Redis:
    """Dependency to get Redis client"""
    if redis_client is None:
        await init_redis()
    return redis_client


async def get_redis_pool() -> redis.Redis:
    """Get Redis client (alias for get_redis for compatibility)"""
    return await get_redis()
