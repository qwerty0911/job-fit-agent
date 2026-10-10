from fastapi import APIRouter, Depends, HTTPException

from schema import ProfileDocumentCreate, ProfileDocumentSearch, ProfileResponse, ProfileSkillsInsert, VectorSearchQueryResult
from service.auth import get_current_user
from service.document_service import (
    create_profile_document as create_profile_document_service,
    search_profile_documents_batch,
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


@router.post("/documents")
async def create_profile_document_endpoint(
    request: ProfileDocumentCreate,
    current_user=Depends(get_current_user),
):
    document_id = await create_profile_document_service(
        request=request,
        user_uuid=current_user["_id"],
    )
    return {"document_id": document_id, "embedding_status": "indexed"}


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
