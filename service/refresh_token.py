import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from redis.exceptions import WatchError

from config import (
    REFRESH_SESSION_MAX_SECONDS,
    REFRESH_TOKEN_TTL_SECONDS,
)
from database import get_redis

def create_refresh_token() -> tuple[str, str, str, str]:
    refresh_token = secrets.token_urlsafe(32)
    token_id = str(uuid4())
    session_id = str(uuid4())
    family_id = str(uuid4())

    return refresh_token, token_id, session_id, family_id


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(
        refresh_token.encode("utf-8")
    ).hexdigest()


async def store_refresh_session(
    *,
    refresh_token: str,
    token_id: str,
    session_id: str,
    family_id: str,
    user_uuid: str,
) -> None:
    redis = get_redis()
    token_hash = hash_refresh_token(refresh_token)

    expires_at = datetime.now(UTC) + timedelta(
        seconds=REFRESH_TOKEN_TTL_SECONDS
    )

    session_data = {
        "token_id": token_id,
        "session_id": session_id,
        "family_id": family_id,
        "user_uuid": user_uuid,
        "status": "active",
        "expires_at": expires_at.isoformat(),
    }

    await redis.set(
        f"refresh:token:{token_hash}",
        json.dumps(session_data),
        ex=REFRESH_TOKEN_TTL_SECONDS,
    )

    await redis.set(
    f"refresh:family:{family_id}",
    "active",
    ex=REFRESH_SESSION_MAX_SECONDS,
    )

async def get_refresh_session(
    refresh_token: str,
) -> dict | None:
    redis = get_redis()
    token_hash = hash_refresh_token(refresh_token)

    session_data = await redis.get(
        f"refresh:token:{token_hash}"
    )

    if session_data is None:
        return None
    
    return json.loads(session_data)

async def rotate_refresh_session(
    refresh_token: str,
) -> tuple[str, dict] | None:
    redis = get_redis()

    old_hash = hash_refresh_token(refresh_token)
    old_key = f"refresh:token:{old_hash}"

    async with redis.pipeline(transaction=True) as pipe:
        while True:
            try:
                await pipe.watch(old_key)

                old_raw = await pipe.get(old_key)

                if old_raw is None:
                    return None

                old_data = json.loads(old_raw)
                family_id = old_data.get("family_id")

                if not family_id:
                    return None

                family_key = f"refresh:family:{family_id}"
                await pipe.watch(family_key)

                family_status = await pipe.get(family_key)

                if family_status != "active":
                    return None

                # 이미 사용된 토큰이면 재사용으로 판단한다.
                if old_data.get("status") != "active":
                    family_ttl = await pipe.ttl(family_key)

                    pipe.multi()

                    if family_ttl > 0:
                        pipe.set(
                            family_key,
                            "revoked",
                            ex=family_ttl,
                        )
                    else:
                        pipe.set(family_key, "revoked")

                    await pipe.execute()
                    return None

                old_ttl = await pipe.ttl(old_key)
                family_ttl = await pipe.ttl(family_key)

                if old_ttl <= 0 or family_ttl <= 0:
                    return None

                new_refresh_token = secrets.token_urlsafe(32)
                new_token_id = str(uuid4())
                new_hash = hash_refresh_token(new_refresh_token)
                new_key = f"refresh:token:{new_hash}"

                new_ttl = min(
                    REFRESH_TOKEN_TTL_SECONDS,
                    family_ttl,
                )

                new_data = {
                    "token_id": new_token_id,
                    "session_id": old_data["session_id"],
                    "family_id": family_id,
                    "user_uuid": old_data["user_uuid"],
                    "status": "active",
                    "expires_at": (
                        datetime.now(UTC)
                        + timedelta(seconds=new_ttl)
                    ).isoformat(),
                }

                old_data["status"] = "used"
                old_data["used_at"] = datetime.now(UTC).isoformat()

                pipe.multi()

                pipe.set(
                    old_key,
                    json.dumps(old_data),
                    ex=old_ttl,
                )

                pipe.set(
                    new_key,
                    json.dumps(new_data),
                    ex=new_ttl,
                )

                await pipe.execute()

                return new_refresh_token, new_data

            except WatchError:
                # 다른 요청이 먼저 토큰을 회전시킨 경우 다시 확인한다.
                continue

async def revoke_refresh_session(
    refresh_token: str,
) -> bool:
    redis = get_redis()

    session_data = await get_refresh_session(refresh_token)

    if session_data is None:
        return False

    family_id = session_data.get("family_id")

    if not family_id:
        return False

    family_key = f"refresh:family:{family_id}"
    family_ttl = await redis.ttl(family_key)

    if family_ttl <= 0:
        return False

    await redis.set(
        family_key,
        "revoked",
        ex=family_ttl,
    )

    return True