from fastapi import APIRouter, Depends, HTTPException

from schema import JobPosting
from service.auth import get_current_user
from service.job_service import get_recommanded_postings


router = APIRouter(prefix="/postings", tags=["postings"])


@router.get("/me", response_model=list[JobPosting], response_model_by_alias=False)
async def get_recommended_postings_endpoint(current_user=Depends(get_current_user)):
    postings = await get_recommanded_postings(current_user["_id"])
    if postings is None:
        raise HTTPException(status_code=404, detail="User not found")
    return postings
