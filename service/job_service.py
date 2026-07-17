from database import get_database
from bson import ObjectId
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
        {
            "$addToSet": {
                "recommanded_postings": {
                    "$each": posting_ids,
                }
            }
        },
    )

    if result.matched_count == 0:
        return None

    return posting_ids


async def get_recommanded_postings(
    user_uuid: UUID | str,
) -> list[JobPosting] | None:
    db = get_database()

    user = await db.users.find_one(
        {"_id": str(user_uuid)},
        {"recommanded_postings": 1},
    )

    if user is None:
        return None

    posting_ids = [
        str(posting_id)
        for posting_id in user.get("recommanded_postings", [])
    ]

    if not posting_ids:
        return []

    # Support both ObjectId and string _id values in job_postings.
    mongo_ids: list[ObjectId | str] = list(posting_ids)
    mongo_ids.extend(
        ObjectId(posting_id)
        for posting_id in posting_ids
        if ObjectId.is_valid(posting_id)
    )

    documents = await db.job_postings.find(
        {"_id": {"$in": mongo_ids}}
    ).to_list(length=len(posting_ids))

    postings_by_id = {
        str(document["_id"]): JobPosting.model_validate({
            **document,
            "_id": str(document["_id"]),
        })
        for document in documents
    }

    # MongoDB $in does not preserve order, so restore the user's saved order.
    return [
        postings_by_id[posting_id]
        for posting_id in posting_ids
        if posting_id in postings_by_id
    ]
