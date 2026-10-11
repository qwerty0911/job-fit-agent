from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from observability import create_langfuse_handler
from schema import ChatRequest, ConversationCreate, ConversationResponse
from service.auth import get_current_user
from service.conversation import (
    create_conversation,
    get_owned_conversation,
    list_user_conversations,
)
from service.conversation_lock import acquire_conversation_lock, release_conversation_lock
from state import GraphContext


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation_endpoint(
    request: ConversationCreate,
    current_user=Depends(get_current_user),
):
    return await create_conversation(owner_user_uuid=current_user["_id"], title=request.title)


@router.get("", response_model=list[ConversationResponse])
async def list_user_conversations_endpoint(current_user=Depends(get_current_user)):
    return await list_user_conversations(owner_user_uuid=current_user["_id"])


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_owned_conversation_endpoint(
    conversation_id: UUID,
    current_user=Depends(get_current_user),
):
    conversation = await get_owned_conversation(
        conversation_id=conversation_id,
        owner_user_uuid=current_user["_id"],
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/{conversation_id}/chat")
async def send_conversation_message_endpoint(
    conversation_id: UUID,
    request: ChatRequest,
    app_request: Request,
    current_user=Depends(get_current_user),
):
    user_uuid = current_user["_id"]
    conversation = await get_owned_conversation(
        conversation_id=conversation_id,
        owner_user_uuid=user_uuid,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation_id_str = str(conversation_id)
    lock_token = await acquire_conversation_lock(conversation_id_str)
    if lock_token is None:
        raise HTTPException(status_code=409, detail="대화가 현재 처리 중입니다.")

    graph_config = {"configurable": {"thread_id": conversation_id_str}}
    langfuse_handler = create_langfuse_handler()
    if langfuse_handler is not None:
        graph_config["callbacks"] = [langfuse_handler]
        graph_config["metadata"] = {
            "langfuse_user_id": user_uuid,
            "langfuse_session_id": conversation_id_str,
            "langfuse_tags": ["job-fit-agent"],
        }

    try:
        result = await app_request.app.state.graph.ainvoke(
            {"jobs_list": [], "match_assessment": None, "response": None},
            config=graph_config,
            context=GraphContext(user_uuid=user_uuid, message=request.message),
        )
    finally:
        await release_conversation_lock(conversation_id_str, lock_token)

    return {"response": result["response"]}
