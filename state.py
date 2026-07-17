from typing import TypedDict,Literal, Optional
from pydantic import BaseModel, Field




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

class JobSearchRequest(BaseModel):
    mode: Literal["keyword_based", "profile_based"] = Field(
        ...,
        description="검색 방법. 사용자 입력 키워드 기반이면 keyword_based, 프로필 기반 추천이면 profile_based"
    )
    keyword: str = Field(
        default="",
        description="검색에 사용할 자연어 키워드. 예: 백엔드 신입 Python"
    )
    job_cd: Optional[str] = Field(
        default=None,
        description="사람인 직무 코드. 모르면 None"
    )
    job_type: Optional[str] = Field(
        default=None,
        description="사람인 근무형태/고용형태 코드. 모르면 None"
    )
    location: Optional[str] = Field(
        default=None,
        description="지역명 또는 지역 코드. 예: 서울"
    )


class GraphState(TypedDict):
    user_uuid: str
    message: str
    
    intent: str

    profile : dict
    jobs_list : list[dict]
    job_search_request : JobSearchRequest

    response : str
