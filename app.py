import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

from api import auth, conversations, health, jobs, postings, profile
from config import CORS_ORIGINS, MONGODB_DB_NAME, MONGODB_URI
from database import (
    close_mongodb_connection,
    close_redis_connection,
    connect_to_mongodb,
    connect_to_redis,
)
from graph import create_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()
    await connect_to_redis()
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
        await close_redis_connection()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(postings.router)
app.include_router(conversations.router)
app.include_router(jobs.router)