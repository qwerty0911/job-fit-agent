import secrets

from database import get_redis

LOCK_TTL_SECONDS = 120
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

def conversation_lock_key(conversation_id: str) -> str:
    return f"lock:conversation:{conversation_id}"


async def acquire_conversation_lock(
    conversation_id: str,
) -> str | None:
    redis = get_redis()
    lock_token = secrets.token_urlsafe(32)

    acquired = await redis.set(
        conversation_lock_key(conversation_id),
        lock_token,
        nx=True,
        ex=LOCK_TTL_SECONDS,
    )

    if not acquired:
        return None

    return lock_token

async def release_conversation_lock(
    conversation_id: str,
    lock_token: str,
) -> None:
    redis = get_redis()

    await redis.eval(
        _RELEASE_LOCK_SCRIPT,
        1,
        conversation_lock_key(conversation_id),
        lock_token,
    )