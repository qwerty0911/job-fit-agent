from datetime import UTC, datetime
from uuid import uuid4, UUID


from database import get_database
from schema import ConversationResponse


async def create_conversation(
    *,
    owner_user_uuid: str,
    title: str,
) -> ConversationResponse:
    db = get_database()

    now = datetime.now(UTC)
    conversation_id = uuid4()

    conversation = {
        "_id": str(conversation_id),
        "owner_user_uuid": owner_user_uuid,
        "title": title,
        "version": 0,
        "created_at": now,
        "updated_at": now,
    }

    await db.conversations.insert_one(conversation)

    return ConversationResponse(
        conversation_id=conversation_id,
        owner_user_uuid=owner_user_uuid,
        title=title,
        version=0,
        created_at=now,
        updated_at=now,
    )


async def list_user_conversations(
    *,
    owner_user_uuid: str,
    limit: int = 20,
) -> list[ConversationResponse]:
    db = get_database()

    cursor = (
        db.conversations
        .find(
            {"owner_user_uuid": owner_user_uuid},
            {
                "_id": 1,
                "owner_user_uuid": 1,
                "title": 1,
                "version": 1,
                "created_at": 1,
                "updated_at": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(limit)
    )

    conversations = await cursor.to_list(length=limit)

    return [
        ConversationResponse(
            conversation_id=conversation["_id"],
            owner_user_uuid=conversation["owner_user_uuid"],
            title=conversation["title"],
            version=conversation.get("version", 0),
            created_at=conversation["created_at"],
            updated_at=conversation["updated_at"],
        )
        for conversation in conversations
    ]

async def get_owned_conversation(
    *,
    conversation_id: UUID,
    owner_user_uuid: str,
) -> ConversationResponse | None:
    db = get_database()

    conversation = await db.conversations.find_one({
        "_id": str(conversation_id),
        "owner_user_uuid": owner_user_uuid,
    })

    if conversation is None:
        return None

    return ConversationResponse(
        conversation_id=conversation["_id"],
        owner_user_uuid=conversation["owner_user_uuid"],
        title=conversation["title"],
        version=conversation.get("version", 0),
        created_at=conversation["created_at"],
        updated_at=conversation["updated_at"],
    )