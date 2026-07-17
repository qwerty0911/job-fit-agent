
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

class ChatRequest(BaseModel):
    user_uuid : UUID
    message: str

class ProfileDocumentCreate(BaseModel):
    user_uuid : UUID
    title : str
    content : str

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
