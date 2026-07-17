from database import get_database
from schema import JobSearchCondition, JobPosting
import re
from uuid import UUID

async def search_jobs(condition:JobSearchCondition) -> list[JobPosting]:
    db = get_database()

    query: dict = {}

    if condition.keyword:
        normalized_keyword = re.sub(r"\s+", "", condition.keyword)
        pattern = r"\s*".join(re.escape(char) for char in normalized_keyword)
        query["job_title_normalized"] = { "$regex": pattern,"$options": "i", }

    if condition.location:
        query["location"] = condition.location

    if condition.job_type:
        query["job_type"] = condition.job_type

    jobs = await db.job_postings.find(query).limit(5).to_list(length=5)

    return [
        JobPosting.model_validate({
            **job,
            "_id": str(job["_id"]),
        })
        for job in jobs
    ]


async def insert_recommand_postings_to_user(
    user_uuid: UUID | str,
    job_postings: list[JobPosting],
) -> list[str] | None:
    db = get_database()
    posting_ids = [posting.id for posting in job_postings]

    result = await db.users.update_one(
        {"_id": str(user_uuid)},
        {"$set": {"recommanded_postings": posting_ids}},
    )

    if result.matched_count == 0:
        return None

    return posting_ids
