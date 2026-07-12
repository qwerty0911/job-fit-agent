from typing import TypedDict,Literal
from pydantic import BaseModel, Field

class GraphState(TypedDict):
    message: str
    response: str
    intent: str


class IntentClassification(BaseModel):
    intent: Literal["search_job", "profile_update", "matching_score", "others"] = Field(
        ...,
        description="사용자 요청의 의도"
    )

    confidence: float = Field(
        description="의도 분류 신뢰도. 0~1",
        ge=0,
        le=1,
    )

    reason: str = Field(description="의도 분류 이유")