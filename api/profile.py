from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from pymongo.errors import DuplicateKeyError

from schema import ProfileDocumentCreate, ProfileDocumentSearch, ProfileResponse, ProfileSkillsInsert, VectorSearchQueryResult
from service.auth import get_current_user
from service.document_service import (
    create_profile_document as create_profile_document_service,
    search_profile_documents_batch,
)
from service.document_job_service import (
    create_document_job,
    delete_document_record,
    save_document_record,
    find_existing_document_job,
)
from service.idempotency import (
    create_request_hash,
    normalize_idempotency_key,
)
from service.profile import add_profile_skills_service, get_profile


router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfileResponse)
async def get_profile_endpoint(current_user=Depends(get_current_user)):
    result = await get_profile(current_user["_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result


@router.post("/add_skills", response_model=ProfileResponse)
async def insert_profile_skills_endpoint(
    request: ProfileSkillsInsert,
    current_user=Depends(get_current_user),
):
    result = await add_profile_skills_service(
        user_uuid=current_user["_id"],
        skill=request.skill,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result

@router.post("/documents", status_code=202)
async def create_profile_document_endpoint(
    request: ProfileDocumentCreate,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
        ),
    ],
    current_user=Depends(get_current_user),
):
    # 1. 키 정규화
    normalized_key = normalize_idempotency_key(idempotency_key)

    # 2. 요청 내용 해시 생성
    request_hash = create_request_hash(
        title=request.title,
        content=request.content,
    )

    # 3. 기존 작업 조회
    existing_job = await find_existing_document_job(
        owner_user_uuid=current_user["_id"],
        idempotency_key=normalized_key,
    )

    # 4. 기존 작업이 있으면 결과 재사용
    if existing_job is not None:
        if existing_job["request_hash"] != request_hash:
            raise HTTPException(
                status_code=409,
                detail="같은 Idempotency-Key로 다른 요청이 사용되었습니다.",
            )

        return {
            "document_id": existing_job["document_id"],
            "job_id": existing_job["_id"],
            "status": existing_job["status"],
        }

    # 5. 기존 작업이 없을 때만 이력서 저장
    document_id = await save_document_record(
        request=request,
        user_uuid=current_user["_id"],
    )

    # 6. 작업 생성
    try:
        job_id = await create_document_job(
            document_id=document_id,
            owner_user_uuid=current_user["_id"],
            idempotency_key=normalized_key,
            request_hash=request_hash,
        )
    except DuplicateKeyError:
        # 동시 요청 중 다른 요청이 먼저 작업을 생성한 경우
        await delete_document_record(
            document_id=document_id,
            owner_user_uuid=current_user["_id"],
        )

        existing_job = await find_existing_document_job(
            owner_user_uuid=current_user["_id"],
            idempotency_key=normalized_key,
        )

        if existing_job is None:
            raise HTTPException(
                status_code=503,
                detail="작업 상태를 확인할 수 없습니다.",
            )

        if existing_job["request_hash"] != request_hash:
            raise HTTPException(
                status_code=409,
                detail="같은 Idempotency-Key로 다른 요청이 사용되었습니다.",
            )

    return {
        "document_id": document_id,
        "job_id": job_id,
        "status": "pending",
    }


@router.post("/documents/search", response_model=list[VectorSearchQueryResult])
async def search_profile_documents_endpoint(
    request: ProfileDocumentSearch,
    current_user=Depends(get_current_user),
):
    return await search_profile_documents_batch(
        user_uuid=current_user["_id"],
        queries=request.queries,
        top_k=request.top_k,
        min_score=request.min_score,
        document_type=request.document_type,
    )
