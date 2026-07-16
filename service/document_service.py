from datetime import UTC, datetime

from bson import ObjectId

from database import get_database
# from service.embedding_service import create_embeddings, split_text
# from service.vector_store import VectorStore


async def save_document_to_mongodb(request) -> ObjectId:
    db = get_database()

    document = {
        "_id": str(request.user_uuid),
        "document_type": "cover_letter",
        "title" : request.title,
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
    # mongodb에 원문 저장
    mongo_document_id = await save_document_to_mongodb(request)

    # # vectorstore에 임베딩
    # document_id = str(mongo_document_id)
    # user_uuid = str(request.user_uuid)
    # version = 1

    # chunks = split_text(request.content)
    # embeddings = await create_embeddings(chunks)

    # await VectorStore.save_chunks(
    #     user_uuid=user_uuid,
    #     document_id=document_id,
    #     version=version,
    #     chunks=chunks,
    #     embeddings=embeddings,
    # )

    # # vectorstore 임베딩 후 mongodb 업데이트
    # db = get_database()

    # await db.profile_documents.update_one(
    #     {"_id": mongo_document_id},
    #     {
    #         "$set": {
    #             "vector_store": {
    #                 "provider": "pinecone",
    #                 "namespace": f"user-{user_uuid}",
    #                 "id_prefix": f"{document_id}:v{version}",
    #                 "version": version,
    #                 "chunk_count": len(chunks),
    #                 "status": "indexed",
    #             }
    #         }
    #     },
    # )

    # ObjectId는 JSON으로 반환할 수 없으므로 API 경계에서 문자열로 변환한다.
    return str(mongo_document_id)
