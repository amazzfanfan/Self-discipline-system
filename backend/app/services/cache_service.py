import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()
redis_client = redis.from_url(settings.REDIS_URL)


async def get_cached(key: str) -> str | None:
    return await redis_client.get(key)


async def set_cached(key: str, value: str, ttl: int = 300):
    await redis_client.setex(key, ttl, value)


async def delete_cached(key: str):
    await redis_client.delete(key)
