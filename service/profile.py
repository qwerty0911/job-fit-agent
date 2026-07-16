from database import get_database
from pymongo import ReturnDocument
from uuid import UUID

from schema import ProfileResponse, ProfileSkillsInsert


async def get_profile(user_uuid: UUID) -> ProfileResponse | None:
    db = get_database()

    # users._id is stored as a string by the login endpoint. Passing a native
    # UUID here makes PyMongo try (and fail) to encode it as BSON UUID data.
    user = await db.users.find_one({"_id": str(user_uuid)})

    if user is None:
        return None

    return ProfileResponse(
        user_uuid=user["_id"],
        name=user.get("name", user.get("user_id", "")),
        skills=user.get("skills", []),
        cover_letters=user.get("cover_letters", []),
    )

async def add_profile_skills_service(
    request: ProfileSkillsInsert,
) -> ProfileResponse | None:

    db = get_database()

    user = await db.users.find_one_and_update(
        {"_id": str(request.user_uuid)},
        {
            "$addToSet": {
                "skills": request.skill
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if user is None:
        return None

    return ProfileResponse(
        user_uuid=user["_id"],
        name=user.get("name", user.get("user_id", "")),
        skills=user.get("skills", []),
        cover_letters=user.get("cover_letters", []),
    )
