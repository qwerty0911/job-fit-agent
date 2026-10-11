import hashlib
import json


def normalize_idempotency_key(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("Idempotency-Key가 비어 있습니다.")

    return value


def create_request_hash(*, title: str, content: str) -> str:
    normalized_payload = {
        "title": title.strip(),
        "content": content.strip(),
    }

    payload = json.dumps(
        normalized_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()