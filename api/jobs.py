from fastapi import APIRouter, Depends, HTTPException

from service.auth import get_current_user
from service.document_job_service import get_document_job_status

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
)

@router.get("/{job_id}")
async def get_job_status(job_id: str, current_user=Depends(get_current_user)):
    job = await get_document_job_status(
        job_id=job_id,
        owner_user_uuid=current_user["_id"],
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="작업을 찾을 수 없습니다.",
        )

    return {
        "job_id": job["_id"],
        "document_id": job["document_id"],
        "status": job["status"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "error": job["error"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }