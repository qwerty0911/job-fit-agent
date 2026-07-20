import json

from llm import get_llm
from schema import JobSearchCondition
from service.document_service import search_profile_documents_batch
from service.job_service import (
    find_job_qualifications_by_company_name,
    insert_recommand_postings_to_user,
    search_jobs,
)
from state import GraphState, IntentClassification, JobMatchAssessment


llm = get_llm("gpt-4o-mini")
augment_llm = get_llm("gpt-4o-mini")

route_llm = llm.with_structured_output(IntentClassification)
job_match_assessment_llm = augment_llm.with_structured_output(
    JobMatchAssessment
)


async def classify_intent(message: str) -> IntentClassification:
    return await route_llm.ainvoke(
        [
            {
                "role": "system",
                "content": """
                            사용자의 요청을 분석해 intent와 필요한 조건을 한 번에 추출한다.

                            intent:
                            - search_job: 키워드 기반 채용공고 검색
                            - matching_score: 특정 회사·직무 지원 적합도 분석
                            - others: 위 두 요청에 해당하지 않음

                            추출 규칙:
                            - search_job이면 keyword, job_title, location, job_type을 추출한다.
                            - matching_score이면 company_name과 job_title을 추출한다.
                            - 메시지에 없는 값은 null로 반환한다.
                            - 회사명과 직무명을 임의로 추측하거나 변경하지 않는다.

                            예시:
                            - "서울 Python 백엔드 공고 찾아줘"
                            → intent=search_job, keyword="Python 백엔드",
                                job_title="백엔드 개발자", location="서울"
                            - "테크웨이브 백엔드 공고에 지원할 만할까?"
                            → intent=matching_score, company_name="테크웨이브",
                                job_title="백엔드"
                            """,
            },
            {
                "role": "user",
                "content": f"사용자 요청: {message}",
            },
        ]
    )


async def route_intent_node(state: GraphState):
    print("intent 및 조건 추출 중")
    result = await classify_intent(state["message"])
    print(f"{result}\n")

    return {
        "intent": result.intent,
        "company_name": result.company_name,
        "job_title": result.job_title,
        "keyword": result.keyword,
        "location": result.location,
        "job_type": result.job_type,
    }


async def job_search(state: GraphState):
    print("\n키워드 기반 검색")

    keyword = state.get("keyword") or state.get("job_title") or ""
    location = state.get("location")
    job_type = state.get("job_type")

    if not keyword:
        return {
            "response": "검색할 직무나 기술 키워드를 알려주세요."
        }

    condition = JobSearchCondition(
        keyword=keyword,
        location=location,
        job_type=job_type,
    )
    jobs = await search_jobs(condition)

    if not jobs:
        return {
            "response": "조건에 맞는 채용 공고를 찾지 못했습니다."
        }

    await insert_recommand_postings_to_user(state["user_uuid"], jobs)

    return {
        "jobs_list": [
            job.model_dump(mode="json")
            for job in jobs
        ]
    }


async def matching_score(state: GraphState):
    print("\n공고 매칭")

    company_name = state.get("company_name")
    job_title = state.get("job_title")

    if not company_name:
        return {
            "response": "지원 적합도를 분석할 회사명을 알려주세요."
        }

    postings = await find_job_qualifications_by_company_name(
        company_name=company_name,
        job_title=job_title,
    )

    # 사용자의 직무 표현이 DB 제목과 다를 수 있으므로 회사명만으로 재검색한다.
    if not postings and job_title:
        postings = await find_job_qualifications_by_company_name(
            company_name=company_name,
        )

    if not postings:
        return {
            "response": (
                f"{company_name}의 채용 공고를 찾지 못했습니다. "
                "회사 이름을 정확하게 입력해주세요."
            )
        }

    posting = postings[0]
    qualifications = list(dict.fromkeys(
        qualification.strip()
        for qualification in posting.qualifications
        if qualification.strip()
    ))

    if not qualifications:
        return {
            "response": (
                f"{posting.company_name} {posting.job_title} 공고에 "
                "분석할 자격요건이 없습니다."
            )
        }

    evidence_results = await search_profile_documents_batch(
        user_uuid=state["user_uuid"],
        queries=qualifications,
        top_k=5,
        min_score=-1.0,
        document_type="resume",
    )

    assessment = await job_match_assessment_llm.ainvoke(
        [
            {
                "role": "system",
                "content": """
                너는 채용 자격요건과 지원자의 이력서 근거를 비교하는 평가자다.
                각 자격요건을 정확히 한 번씩 평가한다.

                판정 규칙:
                - 벡터 유사도 점수는 후보 검색용일 뿐 충족 근거로 사용하지 않는다.
                - 이력서 원문에 명시된 내용만 근거로 사용하고 추측하지 않는다.
                - 직접적인 근거가 있으면 satisfied로 판정한다.
                - 관련 경험은 있으나 일부가 불명확하면 partially_satisfied로 판정한다.
                - 근거가 부족하면 insufficient_evidence로 판정한다.
                - 근거 부족을 경험이 없다는 의미로 단정하지 않는다.
                - evidence에는 판정에 사용한 이력서 문장을 넣는다.
                - gaps에는 지원자가 보완해서 설명할 내용을 넣는다.
                """,
            },
            {
                "role": "user",
                "content": (
                    f"회사명: {posting.company_name}\n"
                    f"직무명: {posting.job_title}\n"
                    "자격요건과 검색 근거:\n"
                    f"{json.dumps(evidence_results, ensure_ascii=False)}"
                ),
            },
        ]
    )

    return {
        "jobs_list": [posting.model_dump(mode="json")],
        "match_assessment": assessment.model_dump(mode="json"),
    }


async def final_node(state: GraphState):
    print("\n최종 답변 생성 중")

    if state.get("response"):
        return {"response": state["response"]}

    assessment = state.get("match_assessment")
    if assessment:
        requirement_lines = [
            (
                f"- [{item['status']}] {item['requirement']}: "
                f"{item['reason']}"
            )
            for item in assessment["requirements"]
        ]
        strengths = "\n".join(
            f"- {strength}"
            for strength in assessment.get("strengths", [])
        ) or "- 확인된 강점 없음"
        gaps = "\n".join(
            f"- {gap}"
            for gap in assessment.get("gaps", [])
        ) or "- 확인된 보완점 없음"

        response = (
            f"{assessment['company_name']} "
            f"{assessment['job_title']} 적합도: "
            f"{assessment['overall_score']}점\n\n"
            "자격요건별 평가\n"
            f"{chr(10).join(requirement_lines)}\n\n"
            "강점\n"
            f"{strengths}\n\n"
            "보완점\n"
            f"{gaps}\n\n"
            f"종합 의견\n{assessment['recommendation']}"
        )
        return {"response": response}

    jobs = state.get("jobs_list")
    if jobs:
        job_lines = [
            (
                f"- {job['company_name']} | {job['job_title']} | "
                f"{job['location']}\n  {job['posting_url']}"
            )
            for job in jobs
        ]
        return {
            "response": (
                "조건에 맞는 채용 공고입니다.\n\n"
                + "\n".join(job_lines)
                + "\n\n추천 공고에 등록했어요."
            )
        }

    if state.get("intent") == "others":
        return {
            "response": (
                "채용 공고 검색이나 특정 회사·직무의 지원 적합도를 "
                "질문해주세요."
            )
        }

    return {"response": "요청을 처리하지 못했습니다."}
