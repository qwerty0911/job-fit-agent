import asyncio
from datetime import UTC, datetime

from bson import ObjectId

from database import get_database
from service.embedding_service import (
    create_embeddings,
    create_query_embedding,
    create_query_embeddings,
    split_text,
)
from service.vector_store import save_chunks, search_user_documents


async def save_document_to_mongodb(request) -> ObjectId:
    db = get_database()

    document = {
        "user_uuid": str(request.user_uuid),
        "document_type": "resume",
        "title": request.title,
        "content": request.content,
        "vector_store": {
            "provider": "pinecone",
            "version": 1,
            "status": "pending",
        },
        "created_at": datetime.now(UTC),
    }

    result = await db.profile_documents.insert_one(document)
    return result.inserted_id


async def create_profile_document(request):
    mongo_document_id = await save_document_to_mongodb(request)
    document_id = str(mongo_document_id)
    user_uuid = str(request.user_uuid)
    version = 1
    db = get_database()

    try:
        chunks = split_text(request.content)
        embeddings = await create_embeddings(chunks)

        await save_chunks(
            user_uuid=user_uuid,
            document_id=document_id,
            document_type="resume",
            title=request.title,
            version=version,
            chunks=chunks,
            embeddings=embeddings,
        )
    except Exception as exc:
        await db.profile_documents.update_one(
            {"_id": mongo_document_id},
            {
                "$set": {
                    "vector_store.status": "failed",
                    "vector_store.error": str(exc),
                }
            },
        )
        raise

    await db.profile_documents.update_one(
        {"_id": mongo_document_id},
        {
            "$set": {
                "vector_store": {
                    "provider": "pinecone",
                    "namespace": f"user-{user_uuid}",
                    "id_prefix": f"{document_id}:v{version}",
                    "version": version,
                    "chunk_count": len(chunks),
                    "status": "indexed",
                }
            }
        },
    )

    return document_id


async def search_profile_documents(
    *,
    user_uuid: str,
    query: str,
    top_k: int = 5,
    min_score: float = 0.7,
    document_type: str | None = None,
) -> list[dict]:
    query_embedding = await create_query_embedding(query)

    return await search_user_documents(
        user_uuid=user_uuid,
        query_embedding=query_embedding,
        top_k=top_k,
        min_score=min_score,
        document_type=document_type,
    )


async def search_profile_documents_batch(
    *,
    user_uuid: str,
    queries: list[str],
    top_k: int = 5,
    min_score: float = 0.7,
    document_type: str | None = None,
) -> list[dict]:
    query_embeddings = await create_query_embeddings(queries)

    matches_by_query = await asyncio.gather(
        *[
            search_user_documents(
                user_uuid=user_uuid,
                query_embedding=query_embedding,
                top_k=top_k,
                min_score=min_score,
                document_type=document_type,
            )
            for query_embedding in query_embeddings
        ]
    )

    return [
        {
            "query": query,
            "matches": matches,
        }
        for query, matches in zip(
            queries,
            matches_by_query,
            strict=True,
        )
    ]
