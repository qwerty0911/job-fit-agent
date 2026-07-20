
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from uuid import UUID

class ChatRequest(BaseModel):
    user_uuid : UUID
    message: str

class ProfileDocumentCreate(BaseModel):
    user_uuid : UUID
    title : str
    content : str

class ProfileDocumentSearch(BaseModel):
    user_uuid: UUID
    queries: list[str] = Field(min_length=1, max_length=20)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = 0.7
    document_type: Literal["resume", "cover_letter"] | None = None

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, queries: list[str]) -> list[str]:
        cleaned_queries = [query.strip() for query in queries]

        if any(not query for query in cleaned_queries):
            raise ValueError("검색어는 비어 있을 수 없습니다.")

        return cleaned_queries

class VectorSearchMetadata(BaseModel):
    document_id: str
    document_type: str
    title: str
    version: int
    chunk_index: int
    text: str

class VectorSearchResult(BaseModel):
    id: str
    score: float
    metadata: VectorSearchMetadata

class VectorSearchQueryResult(BaseModel):
    query: str
    matches: list[VectorSearchResult]

class LoginRequest(BaseModel):
    user_id : str

class CoverLetterResponse(BaseModel):
    title: str
    content: str

class ProfileResponse(BaseModel):
    user_uuid: UUID
    name: str
    skills: list[str] = Field(default_factory=list)
    cover_letters: list[CoverLetterResponse] = Field(default_factory=list)

class ProfileSkillsInsert(BaseModel):
    user_uuid: UUID
    skill: str

class ProfileCoverletterInsert(BaseModel):
    user_uuid: UUID
    title: str
    content: str

class JobSearchCondition(BaseModel):
    keyword: str = ""
    location: str | None = None
    job_type: str | None = None

class JobPosting(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    company_name: str
    job_title: str
    job_title_normalized: str
    tech_stack: list[str]
    qualifications : list[str]
    preferred_qualifications : list[str]
    location : str
    experience : str
    posting_url : str


class JobQualificationPosting(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    company_name: str
    job_title: str
    qualifications: list[str] = Field(default_factory=list)
