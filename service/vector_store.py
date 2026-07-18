import asyncio
from functools import lru_cache
from typing import Any

from pinecone import Pinecone

from config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_HOST,
    PINECONE_INDEX_NAME,
)


def user_namespace(user_uuid: str) -> str:
    return f"user-{user_uuid}"


@lru_cache(maxsize=1)
def _get_index():
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY가 설정되지 않았습니다.")

    if not PINECONE_INDEX_HOST and not PINECONE_INDEX_NAME:
        raise RuntimeError(
            "PINECONE_INDEX_HOST 또는 PINECONE_INDEX_NAME이 설정되지 않았습니다."
        )

    client = Pinecone(api_key=PINECONE_API_KEY)

    if PINECONE_INDEX_HOST:
        return client.Index(host=PINECONE_INDEX_HOST)

    return client.Index(PINECONE_INDEX_NAME)


async def save_chunks(
    *,
    user_uuid: str,
    document_id: str,
    document_type: str,
    title: str,
    version: int,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("청크와 임베딩 개수가 일치하지 않습니다.")

    if not chunks:
        raise ValueError("저장할 문서 내용이 없습니다.")

    vectors = [
        {
            "id": f"{document_id}:v{version}:chunk:{chunk_index}",
            "values": embedding,
            "metadata": {
                "document_id": document_id,
                "document_type": document_type,
                "title": title,
                "version": version,
                "chunk_index": chunk_index,
                "text": chunk,
            },
        }
        for chunk_index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings, strict=True)
        )
    ]

    index = _get_index()
    await asyncio.to_thread(
        index.upsert,
        vectors=vectors,
        namespace=user_namespace(user_uuid),
    )


async def search_user_documents(
    *,
    user_uuid: str,
    query_embedding: list[float],
    top_k: int = 5,
    document_type: str | None = None,
) -> list[dict[str, Any]]:
    if top_k < 1:
        raise ValueError("top_k는 1 이상이어야 합니다.")

    query_filter = None
    if document_type:
        query_filter = {
            "document_type": {"$eq": document_type},
        }

    index = _get_index()
    query_kwargs: dict[str, Any] = {
        "namespace": user_namespace(user_uuid),
        "vector": query_embedding,
        "top_k": top_k,
        "include_metadata": True,
    }
    if query_filter:
        query_kwargs["filter"] = query_filter

    result = await asyncio.to_thread(
        index.query,
        **query_kwargs,
    )

    matches = getattr(result, "matches", None)
    if matches is None and isinstance(result, dict):
        matches = result.get("matches", [])

    return [
        {
            "id": match["id"] if isinstance(match, dict) else match.id,
            "score": (
                match["score"] if isinstance(match, dict) else match.score
            ),
            "metadata": (
                match.get("metadata", {})
                if isinstance(match, dict)
                else (match.metadata or {})
            ),
        }
        for match in (matches or [])
    ]
