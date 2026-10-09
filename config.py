import os
from dotenv import load_dotenv

load_dotenv()

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://api.openai.com/v1",
)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "text-embedding-3-large",
)

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "job_matcher")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
PINECONE_INDEX_HOST = os.getenv("PINECONE_INDEX_HOST") or None

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY") or None
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY") or None
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL") or None
LANGFUSE_TRACING_ENVIRONMENT = os.getenv(
    "LANGFUSE_TRACING_ENVIRONMENT",
    "development",
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "job-fit-agent")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "job-fit-api")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
)

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY가 설정되지 않았습니다.")

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

REFRESH_TOKEN_TTL_SECONDS = int(
    os.getenv("REFRESH_TOKEN_TTL_SECONDS", "1209600")
)

REFRESH_SESSION_MAX_SECONDS = int(
    os.getenv("REFRESH_SESSION_MAX_SECONDS", "2592000")
)

REFRESH_COOKIE_SECURE = os.getenv(
    "REFRESH_COOKIE_SECURE",
    "false",
).lower() == "true"

REFRESH_COOKIE_SAMESITE = os.getenv(
    "REFRESH_COOKIE_SAMESITE",
    "lax",
)