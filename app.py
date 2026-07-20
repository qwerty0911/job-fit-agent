from contextlib import asynccontextmanager
from datetime import UTC, datetime
import unicodedata
from uuid import uuid4, UUID

from fastapi import FastAPI, HTTPException
from pymongo.errors import DuplicateKeyError

from database import close_mongodb_connection, connect_to_mongodb, get_database
from graph import graph
from schema import *
from service.profile import get_profile, add_profile_skills_service
from service.job_service import get_recommanded_postings

from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()

    try:
        yield
    finally:
        await close_mongodb_connection()


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from service.document_service import (
    create_profile_document as create_profile_document_service,
    search_profile_documents_batch,
)


def normalize_user_id(user_id: str) -> str:
    return unicodedata.normalize("NFKC", user_id).strip().casefold()



@app.get("/health")
async def health():
    database = get_database()
    await database.command("ping")
    return {"status": "ok", "mongodb": "connected"}


@app.post("/chat")
async def chat(request: ChatRequest):
    result = await graph.ainvoke({
        "user_uuid": str(request.user_uuid),
        "message": request.message,
    })

    return {"response": result["response"]}

@app.get("/profile/{user_uuid}", response_model=ProfileResponse)
async def get_profile_endpoint(user_uuid: UUID):
    result = await get_profile(user_uuid)

    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return result

@app.post("/profile/add_skills", response_model=ProfileResponse)
async def insert_profile_skills(request: ProfileSkillsInsert):
    result = await add_profile_skills_service(request)

    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return result

@app.post("/profile/documents")
async def create_profile_document_endpoint(request: ProfileDocumentCreate):
    document_id = await create_profile_document_service(request)

    return {
        "document_id": document_id,
        "embedding_status": "indexed",
    }

@app.post(
    "/profile/documents/search",
    response_model=list[VectorSearchQueryResult],
)
async def search_profile_documents_endpoint(
    request: ProfileDocumentSearch,
):
    return await search_profile_documents_batch(
        user_uuid=str(request.user_uuid),
        queries=request.queries,
        top_k=request.top_k,
        min_score=request.min_score,
        document_type=request.document_type,
    )

@app.get(
    "/postings/{user_uuid}",
    response_model=list[JobPosting],
    response_model_by_alias=False,
)
async def get_recommended_postings_endpoint(user_uuid: UUID):
    postings = await get_recommanded_postings(user_uuid)

    if postings is None:
        raise HTTPException(status_code=404, detail="User not found")

    return postings


@app.post("/login")
async def login(request: LoginRequest):
    db = get_database()

    user_id = request.user_id.strip()
    if not 2 <= len(user_id) <= 20:
        raise HTTPException(
            status_code=422,
            detail="아이디는 2~20자로 입력해주세요.",
        )

    user_id_key = normalize_user_id(user_id)
    new_user_uuid = str(uuid4())

    try:
        result = await db.users.update_one(
            {"user_id_key": user_id_key},
            {
                "$setOnInsert": {
                    "_id": new_user_uuid,
                    "user_id": user_id,
                    "user_id_key": user_id_key,
                    "created_at": datetime.now(UTC),
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        # 같은 아이디로 동시에 첫 요청이 들어온 경우
        result = None

    user = await db.users.find_one({"user_id_key": user_id_key})
    is_new_user = result is not None and result.upserted_id is not None

    return {
        "user_uuid": user["_id"],
        "user_id": user["user_id"],
        "is_new_user": is_new_user,
        "message": "새 사용자가 생성되었습니다."
        if is_new_user
        else "로그인 성공",
    }
