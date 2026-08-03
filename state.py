from dataclasses import dataclass
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    intent: Literal["search_job", "matching_score", "others"] = Field(
        ...,
        description="사용자 요청의 의도",
    )
    company_name: str | None = None
    job_title: str | None = None
    keyword: str | None = None
    location: str | None = None
    job_type: str | None = None
    posting_index: int | None = Field(
        default=None,
        ge=0,
        description="최근 검색 결과에서 선택한 공고의 0부터 시작하는 순번",
    )
    confidence: float = Field(
        description="의도 분류 신뢰도. 0~1",
        ge=0,
        le=1,
    )
    reason: str = Field(description="의도 분류 이유")


class RequirementAssessment(BaseModel):
    requirement: str
    status: Literal[
        "satisfied",
        "partially_satisfied",
        "insufficient_evidence",
    ]
    reason: str
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class JobMatchAssessment(BaseModel):
    company_name: str
    job_title: str
    overall_score: int = Field(ge=0, le=100)
    requirements: list[RequirementAssessment]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    recommendation: str


@dataclass(frozen=True)
class GraphContext:
    """Per-request values that must not be persisted in checkpoints."""

    user_uuid: str
    message: str


class GraphState(TypedDict, total=False):
    intent: str
    company_name: str | None
    job_title: str | None
    keyword: str | None
    location: str | None
    job_type: str | None
    posting_index: int | None

    recent_posting_ids: list[str]
    selected_posting_id: str | None

    jobs_list: list[dict]
    match_assessment: dict | None
    response: str | None
