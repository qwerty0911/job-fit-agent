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


async def save_document_to_mongodb(
        request,
        user_uuid:str
        ) -> ObjectId:
    db = get_database()

    document = {
        "user_uuid": user_uuid,
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


async def create_profile_document(
        *,
        request
        ,user_uuid:str):
    mongo_document_id = await save_document_to_mongodb(request=request, user_uuid=user_uuid)
    document_id = str(mongo_document_id)
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

    async def search_one_query(
        query_embedding: list[float],
    ) -> list[dict]:
        matches = await search_user_documents(
            user_uuid=user_uuid,
            query_embedding=query_embedding,
            top_k=min(top_k * 3, 50),
            min_score=min_score,
            document_type=document_type,
        )

        active_matches = await filter_active_document_matches(
            user_uuid=user_uuid,
            matches=matches,
        )

        return active_matches[:top_k]

    matches_by_query = await asyncio.gather(
        *[
            search_one_query(query_embedding)
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

async def filter_active_document_matches(
    *,
    user_uuid: str,
    matches: list[dict],
) -> list[dict]:
    if not matches:
        return []

    document_ids = {
        match["metadata"]["document_id"]
        for match in matches
        if match.get("metadata", {}).get("document_id")
    }

    object_ids = []
    for document_id in document_ids:
        try:
            object_ids.append(ObjectId(document_id))
        except Exception:
            continue

    if not object_ids:
        return []

    db = get_database()

    documents = await db.profile_documents.find(
        {
            "_id": {"$in": object_ids},
            "user_uuid": user_uuid,
            "status": "active",
        },
        {
            "_id": 1,
            "active_version": 1,
        },
    ).to_list(length=None)

    active_versions = {
        str(document["_id"]): document.get("active_version")
        for document in documents
    }

    return [
        match
        for match in matches
        if (
            match["metadata"].get("document_id") in active_versions
            and match["metadata"].get("version")
            == active_versions[match["metadata"]["document_id"]]
        )
    ]