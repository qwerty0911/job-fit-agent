from fastapi import APIRouter

from database import get_database, get_redis


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_endpoint():
    database = get_database()
    redis = get_redis()

    await redis.ping()
    await database.command("ping")

    return {
        "status": "ok",
        "mongodb": "connected",
        "redis": "connected",
    }
