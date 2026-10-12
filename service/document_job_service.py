from datetime import UTC, datetime, timedelta
from uuid import uuid4

from config import DOCUMENT_JOB_LEASE_SECONDS

from bson import ObjectId
from pymongo import ReturnDocument

from database import get_database
from service.embedding_service import create_embeddings, split_text
from service.vector_store import (
    delete_document_vectors,
    save_chunks,
)

async def create_document_job(
    *,
    document_id: str,
    owner_user_uuid: str,
    version: int,
    idempotency_key: str,
    request_hash: str,
) -> str:
    job_id = str(uuid4())
    now = datetime.now(UTC)

    job = {
        "_id": job_id,
        "job_type": "document_indexing",
        "document_id": document_id,
        "owner_user_uuid": owner_user_uuid,
        "version": version,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "status": "pending",
        "attempts": 0,
        "max_attempts": 3,
        "error": None,
        "lease_until": None,
        "created_at": now,
        "updated_at": now,
    }

    db = get_database()
    await db.document_jobs.insert_one(job)

    return job_id

# MongoDB에 이력서만 저장
# vector_store.status = "pending"
# document_id 반환
async def save_document_record(
    *,
    request,
    user_uuid: str,
):
    document = {
        "user_uuid": user_uuid,
        "document_type": "resume",
        "title": request.title,
        "content": request.content,

        # 문서 버전 관리 필드
        "current_version": 1,
        "active_version": None,
        "status": "indexing",

        "vector_store": {
            "provider": "pinecone",
            "version": 1,
            "status": "pending",
        },
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    db = get_database()
    result = await db.profile_documents.insert_one(document)

    document_id = str(result.inserted_id)

    await save_document_version(
        document_id=document_id,
        owner_user_uuid=user_uuid,
        version=1,
        title=request.title,
        content=request.content,
    )

    return str(result.inserted_id)

async def claim_document_job(job_id: str) -> dict | None:
    db = get_database()
    now = datetime.now(UTC)
    lease_until = now + timedelta(
        seconds=DOCUMENT_JOB_LEASE_SECONDS
    )

    # pending 작업 하나만 원자적으로 running으로 변경
    job = await db.document_jobs.find_one_and_update(
        {
            "_id": job_id,
            "$or": [
                {
                    "status": "pending",
                },
                {
                    "status": "running",
                    "lease_until": {
                        "$lte": now,
                    },
                },
            ],
            "$expr": {
                "$lt": ["$attempts", "$max_attempts"],
            },
        },
        {
            "$set": {
                "status": "running",
                "lease_until": lease_until,
                "updated_at": now,
            },
            "$inc": {
                "attempts": 1,
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    return job


async def process_document_job(job_id: str) -> None:
    db = get_database()

    job = await claim_document_job(job_id)

    if job is None:
        raise ValueError("처리할 수 없는 작업입니다.")

    document_id = job["document_id"]
    owner_user_uuid = job["owner_user_uuid"]
    version = job["version"]

    try:
        document = await db.profile_documents.find_one(
            {
                "_id": ObjectId(document_id),
                "user_uuid": owner_user_uuid,
            }
        )

        if document is None:
            raise ValueError("이력서 문서를 찾을 수 없습니다.")

        version_document = await db.document_versions.find_one(
            {
                "document_id": document_id,
                "owner_user_uuid": owner_user_uuid,
                "version": version,
            }
        )

        if version_document is None:
            raise ValueError(
                f"문서 버전을 찾을 수 없습니다: {document_id}:v{version}"
            )

        chunks = split_text(version_document["content"])
        embeddings = await create_embeddings(chunks)

        await save_chunks(
            user_uuid=owner_user_uuid,
            document_id=document_id,
            document_type=document["document_type"],
            title=version_document["title"],
            version=version,
            chunks=chunks,
            embeddings=embeddings,
        )

        await db.document_versions.update_one(
            {
                "document_id": document_id,
                "owner_user_uuid": owner_user_uuid,
                "version": version,
            },
            {
                "$set": {
                    "index_status": "succeeded",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        now = datetime.now(UTC)

        await db.document_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "succeeded",
                    "error": None,
                    "updated_at": now,
                }
            },
        )

        await db.profile_documents.update_one(
            {
                "_id": ObjectId(document_id),
                "user_uuid": owner_user_uuid,
                "$or": [
                    {"active_version": {"$exists": False}},
                    {"active_version": None},
                    {"active_version": {"$lt": version}},
                ],
            },
            {
                "$set": {
                    "status": "active",
                    "active_version": version,
                    "vector_store.status": "indexed",
                    "vector_store.chunk_count": len(chunks),
                    "vector_store.namespace": f"user-{owner_user_uuid}",
                    "vector_store.id_prefix": f"{document_id}:v{version}",
                    "vector_store.updated_at": datetime.now(UTC),
                    "vector_store.version": version,
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    except Exception as exc:
        await db.document_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc),
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        await db.profile_documents.update_one(
            {
                "_id": ObjectId(document_id),
                "user_uuid": owner_user_uuid,
                "$or": [
                    {"active_version": {"$exists": False}},
                    {"active_version": None},
                ],
            },
            {
                "$set": {
                    "vector_store.status": "failed",
                    "vector_store.error": str(exc),
                    "vector_store.updated_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        # 활성 버전이 아직 없을 때만 문서 전체를 failed로 표시한다.
        # 이미 활성 버전이 있으면 새 버전 실패가 기존 정상 버전을 숨기면 안 된다.
        await db.profile_documents.update_one(
            {
                "_id": ObjectId(document_id),
                "user_uuid": owner_user_uuid,
                "$or": [
                    {"active_version": {"$exists": False}},
                    {"active_version": None},
                ],
            },
            {
                "$set": {
                    "status": "failed",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        await db.document_versions.update_one(
            {
                "document_id": document_id,
                "owner_user_uuid": owner_user_uuid,
                "version": version,
            },
            {
                "$set": {
                    "index_status": "failed",
                    "error": str(exc),
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        raise

async def get_document_job_status(
    *,
    job_id: str,
    owner_user_uuid: str,
) -> dict | None:
    db = get_database()

    job = await db.document_jobs.find_one(
        {
            "_id": job_id,
            "owner_user_uuid": owner_user_uuid,
        },
        {
            "_id": 1,
            "document_id": 1,
            "version": 1,
            "status": 1,
            "attempts": 1,
            "max_attempts": 1,
            "error": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    )

    return job


async def find_existing_document_job(
    *,
    owner_user_uuid: str,
    idempotency_key: str,
) -> dict | None:
    db = get_database()

    return await db.document_jobs.find_one(
        {
            "owner_user_uuid": owner_user_uuid,
            "job_type": "document_indexing",
            "idempotency_key": idempotency_key,
        }
    )


async def delete_document_record(
    *,
    document_id: str,
    owner_user_uuid: str,
) -> None:
    db = get_database()

    await db.profile_documents.delete_one(
        {
            "_id": ObjectId(document_id),
            "user_uuid": owner_user_uuid,
        }
    )

async def save_document_version(
    *,
    document_id: str,
    owner_user_uuid: str,
    version: int,
    title: str,
    content: str,
) -> None:
    db = get_database()
    now = datetime.now(UTC)

    await db.document_versions.insert_one(
        {
            "_id": f"{document_id}:v{version}",
            "document_id": document_id,
            "owner_user_uuid": owner_user_uuid,
            "version": version,
            "title": title,
            "content": content,
            "index_status": "pending",
            "created_at": now,
            "updated_at": now,
        }
    )

async def create_document_version(
    *,
    document_id: str,
    owner_user_uuid: str,
    title: str,
    content: str,
) -> int:
    db = get_database()
    now = datetime.now(UTC)

    document = await db.profile_documents.find_one_and_update(
        {
            "_id": ObjectId(document_id),
            "user_uuid": owner_user_uuid,
            "status": {"$ne": "deleted"},
        },
        {
            "$inc": {
                "current_version": 1,
            },
            "$set": {
                "title": title,
                "content": content,
                "status": "indexing",
                "updated_at": now,
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if document is None:
        raise ValueError("수정할 문서를 찾을 수 없습니다.")

    version = document["current_version"]

    await save_document_version(
        document_id=document_id,
        owner_user_uuid=owner_user_uuid,
        version=version,
        title=title,
        content=content,
    )

    return version


async def mark_document_deleted(
    *,
    document_id: str,
    owner_user_uuid: str,
) -> bool:
    db = get_database()
    now = datetime.now(UTC)

    result = await db.profile_documents.update_one(
        {
            "_id": ObjectId(document_id),
            "user_uuid": owner_user_uuid,
            "status": {"$ne": "deleted"},
        },
        {
            "$set": {
                "status": "deleted",
                "deleted_at": now,
                "updated_at": now,
            }
        },
    )

    return result.modified_count == 1

async def create_document_cleanup_job(
    *,
    document_id: str,
    owner_user_uuid: str,
) -> str:
    db = get_database()

    idempotency_key = f"cleanup:{document_id}"

    existing_job = await db.document_jobs.find_one(
        {
            "owner_user_uuid": owner_user_uuid,
            "job_type": "document_cleanup",
            "idempotency_key": idempotency_key,
        }
    )

    if existing_job is not None:
        return existing_job["_id"]

    return await create_document_job(
        document_id=document_id,
        owner_user_uuid=owner_user_uuid,
        version=None,
        idempotency_key=idempotency_key,
        request_hash="",
        job_type="document_cleanup",
    )

async def process_document_cleanup_job(job_id: str) -> None:
    db = get_database()

    job = await claim_document_job(job_id)

    if job is None:
        raise ValueError("처리할 수 없는 정리 작업입니다.")

    document_id = job["document_id"]
    owner_user_uuid = job["owner_user_uuid"]

    try:
        await delete_document_vectors(
            user_uuid=owner_user_uuid,
            document_id=document_id,
        )

        await db.document_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "succeeded",
                    "error": None,
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    except Exception as exc:
        await db.document_jobs.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc),
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        raise