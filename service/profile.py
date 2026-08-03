from database import get_database
from pymongo import ReturnDocument
from uuid import UUID

from schema import (
    ProfileCoverletterInsert,
    ProfileDocumentResponse,
    ProfileResponse,
    ProfileSkillsInsert,
)


async def get_profile_documents(
    user_uuid: UUID | str,
) -> list[ProfileDocumentResponse]:
    db = get_database()

    cursor = db.profile_documents.find(
        {"user_uuid": str(user_uuid)}
    ).sort("created_at", -1)
    documents = await cursor.to_list(length=100)

    return [
        ProfileDocumentResponse(
            document_id=str(document["_id"]),
            document_type=document.get("document_type", "resume"),
            title=document.get("title", ""),
            content=document.get("content", ""),
            embedding_status=document.get("vector_store", {}).get("status"),
            created_at=document.get("created_at"),
        )
        for document in documents
    ]


async def get_profile(user_uuid: UUID) -> ProfileResponse | None:
    db = get_database()

    # users._id is stored as a string by the login endpoint. Passing a native
    # UUID here makes PyMongo try (and fail) to encode it as BSON UUID data.
    user = await db.users.find_one({"_id": str(user_uuid)})

    if user is None:
        return None

    documents = await get_profile_documents(user_uuid)

    return ProfileResponse(
        user_uuid=user["_id"],
        name=user.get("name", user.get("user_id", "")),
        skills=user.get("skills", []),
        cover_letters=user.get("cover_letters", []),
        documents=documents,
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

    documents = await get_profile_documents(request.user_uuid)

    return ProfileResponse(
        user_uuid=user["_id"],
        name=user.get("name", user.get("user_id", "")),
        skills=user.get("skills", []),
        cover_letters=user.get("cover_letters", []),
        documents=documents,
    )


async def add_profile_coverletter_service(
    request: ProfileCoverletterInsert,
) -> ProfileResponse | None:
    db = get_database()

    user = await db.users.find_one_and_update(
        {"_id": str(request.user_uuid)},
        {
            "$push": {
                "cover_letters": {
                    "title": request.title,
                    "content": request.content,
                }
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if user is None:
        return None

    documents = await get_profile_documents(request.user_uuid)

    return ProfileResponse(
        user_uuid=user["_id"],
        name=user.get("name", user.get("user_id", "")),
        skills=user.get("skills", []),
        cover_letters=user.get("cover_letters", []),
        documents=documents,
    )
