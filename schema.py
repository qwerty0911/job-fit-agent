
from pydantic import BaseModel, Field
from uuid import UUID

class ChatRequest(BaseModel):
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
