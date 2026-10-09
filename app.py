import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import unicodedata
from uuid import uuid4, UUID

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from config import CORS_ORIGINS, MONGODB_DB_NAME, MONGODB_URI
from database import close_mongodb_connection, connect_to_mongodb, get_database
from graph import create_graph
from observability import create_langfuse_handler
from schema import *
from state import GraphContext
from service.profile import get_profile, add_profile_skills_service
from service.job_service import get_recommanded_postings

from fastapi import Depends
from service.auth import (
    get_current_user,
    normalize_user_id,
    hash_password,
    verify_password,
    create_access_token,
)

from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()
    checkpoint_client = None

    try:
        checkpoint_client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5_000,
        )
        checkpointer = await asyncio.to_thread(
            MongoDBSaver,
            client=checkpoint_client,
            db_name=MONGODB_DB_NAME,
            checkpoint_collection_name="langgraph_checkpoints",
            writes_collection_name="langgraph_checkpoint_writes",
        )
        app.state.graph = create_graph(checkpointer=checkpointer)
        yield
    finally:
        if checkpoint_client is not None:
            checkpoint_client.close()
        await close_mongodb_connection()


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from service.document_service import (
    create_profile_document as create_profile_document_service,
    search_profile_documents_batch,
)

@app.get("/health")
async def health():
    database = get_database()
    await database.command("ping")
    return {"status": "ok", "mongodb": "connected"}

@app.get("/auth/me")
async def get_me(current_user=Depends(get_current_user)):
    return {
        "user_uuid": current_user["_id"],
        "user_id": current_user["user_id"],
    }


@app.post("/chat")
async def chat(request: ChatRequest,current_user=Depends(get_current_user)):
    user_uuid = current_user["_id"]
    graph_config = {"configurable": {"thread_id": user_uuid}}
    langfuse_handler = create_langfuse_handler()

    if langfuse_handler is not None:
        graph_config["callbacks"] = [langfuse_handler]
        graph_config["metadata"] = {
            "langfuse_user_id": user_uuid,
            "langfuse_session_id": user_uuid,
            "langfuse_tags": ["job-fit-agent"],
        }

    result = await app.state.graph.ainvoke(
        {
            # 체크포인트에 남아 있는 직전 실행 결과가 새 응답에 섞이지
            # 않도록 실행 단위 결과 필드를 초기화한다.
            "jobs_list": [],
            "match_assessment": None,
            "response": None,
        },
        config=graph_config,
        context=GraphContext(
            user_uuid=user_uuid,
            message=request.message,
        ),
    )

    return {"response": result["response"]}

@app.get("/profile/me", response_model=ProfileResponse)
async def get_profile_endpoint(current_user=Depends(get_current_user)):
    user_uuid = current_user["_id"]
    result = await get_profile(user_uuid)

    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return result

@app.post("/profile/add_skills", response_model=ProfileResponse)
async def insert_profile_skills(request: ProfileSkillsInsert, current_user=Depends(get_current_user)):
    user_uuid = current_user["_id"]
    result = await add_profile_skills_service(
        user_uuid=user_uuid,
        skill=request.skill,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return result

@app.post("/profile/documents")
async def create_profile_document_endpoint(request: ProfileDocumentCreate, current_user=Depends(get_current_user)):
    user_uuid = current_user["_id"]
    document_id = await create_profile_document_service(request=request, user_uuid=user_uuid)

    return {
        "document_id": document_id,
        "embedding_status": "indexed",
    }

@app.post(
    "/profile/documents/search",
    response_model=list[VectorSearchQueryResult],
)
async def search_profile_documents_endpoint(
    request: ProfileDocumentSearch,current_user=Depends(get_current_user)
):
    user_uuid = current_user["_id"]
    
    return await search_profile_documents_batch(
        user_uuid=user_uuid,
        queries=request.queries,
        top_k=request.top_k,
        min_score=request.min_score,
        document_type=request.document_type,
    )

@app.get(
    "/postings/me",
    response_model=list[JobPosting],
    response_model_by_alias=False,
)
async def get_recommended_postings_endpoint(current_user=Depends(get_current_user)):
    user_uuid = current_user["_id"]
    postings = await get_recommanded_postings(user_uuid)

    if postings is None:
        raise HTTPException(status_code=404, detail="User not found")

    return postings


@app.post("/signup",
        response_model=SignupResponse,
        status_code=201,)
async def signup(request: SignupRequest):
    db = get_database()
    user_id = request.user_id
    user_id_key = normalize_user_id(user_id)
    password_hash = hash_password(request.password)
    new_user_uuid = str(uuid4())

    if not 2 <= len(user_id_key) <= 20:
        raise HTTPException(
            status_code=422,
            detail="아이디는 2~20자로 입력해주세요.",
        )

    try:
        await db.users.insert_one({
            "_id": new_user_uuid,
            "user_id": user_id,
            "user_id_key": user_id_key,
            "password_hash": password_hash,
            "created_at": datetime.now(UTC),
        })
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="이미 사용 중인 아이디입니다.",
    )

    return SignupResponse(
        user_uuid=new_user_uuid,
        user_id=user_id,
        message="회원가입이 완료되었습니다.",
    )


@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    db = get_database()

    user_id = request.user_id.strip()
    user_id_key = normalize_user_id(user_id)

    user = await db.users.find_one({
        "user_id_key": user_id_key
    })

    if (
        user is None
        or not user.get("password_hash")
        or not verify_password(
            request.password,
            user["password_hash"],
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user["_id"])

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_uuid=user["_id"],
    )
