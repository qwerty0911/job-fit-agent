from typing import Any

from pymongo import AsyncMongoClient

from config import MONGODB_DB_NAME, MONGODB_URI


_client: AsyncMongoClient[dict[str, Any]] | None = None
_database: Any | None = None


async def connect_to_mongodb() -> None:
    """Create one MongoDB connection pool for the application."""
    global _client, _database

    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI가 설정되지 않았습니다.")

    client = AsyncMongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5_000,
    )

    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        raise

    _client = client
    _database = client[MONGODB_DB_NAME]


async def close_mongodb_connection() -> None:
    """Close the MongoDB connection pool during application shutdown."""
    global _client, _database

    if _client is not None:
        await _client.close()

    _client = None
    _database = None


def get_database() -> Any:
    """Return the connected database for repositories and graph nodes."""
    if _database is None:
        raise RuntimeError("MongoDB가 연결되지 않았습니다.")

    return _database
