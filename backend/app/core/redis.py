"""Redis connection layer.

Used from V1 onward for the JWT logout denylist; exposed now so health
readiness checks and future modules share one client.
"""
import redis

from app.core.config import settings

redis_client: redis.Redis = redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis() -> redis.Redis:
    return redis_client
