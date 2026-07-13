from state import GraphState
from state import IntentClassification, JobSearchRequest
from llm import get_llm

llm=get_llm("openai/gpt-5.4")
augment_llm= get_llm("openai/gpt-5.6-terra")

llm_with_structured_output = llm.with_structured_output(IntentClassification)
llm_with_structured_output2 = llm.with_structured_output(JobSearchRequest)

async def classify_intent(user_reply: str) -> IntentClassification:
    result = await llm_with_structured_output.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "너는 사용자의 요청이 프로필 업데이트(profile_update)인지, 공고 검색(serach_job)인지, 공고와 내 프로필의 매칭점수(matching_score)를 요청하는거지 분류한다. "
                    "search_job, profile_update, matching_score 중 하나로 반환한다.\n"
                    "의도가 명확하지 않거나 해당사항이 없다면 others를 반환한다\n"
                    "- search_job: ai-agent 개발 공고 정리해줘\n"
                    "- profile_update: 최근에 spring-framework 공부중이야\n"
                    "- matching_score: 삼성sds 백엔드 개발공고는 내가 지원하기에 어때"
                ),
            },
            {
                "role": "user",
                "content": f"사용자 요청: {user_reply}",
            },
        ]
    )

    return result

async def parse_job_search_request(user_reply: str) -> JobSearchRequest:
    result = await llm_with_structured_output2.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "너의 목표는 두개야 "
                    "1. profile기반 검색이 필요한지 keyword기반 검색이 필요한지 검색해줘"
                    "- 나에게 맞는 공고 찾아줘 -> profile_based"
                    "- 근무지가 서울인 백엔드 공고 찾아줘 -> keywork_based"
                    "2. keyword_based라면 role, level, location을 추출해줘"
                    "- 판교가 근무지인 ai 개발 정규직 공고 찾아줘 -> keyword : ai 개발, location : 판교, job_type : 정규직"
                ),
            },
            {
                "role": "user",
                "content": f"사용자 요청: {user_reply}",
            },
        ]
    )

    return result

async def route_intent_node(state: GraphState):
    message = state["message"]
    print(f"intent 분류중")
    result = await classify_intent(message)
    print(f"{result}\n ")

    return {
        "intent": result.intent,
        # "confidence": result.confidence,
        # "reason": result.reason,
    }

#공고를 검색하는 노드
async def parse_job_search_request_node(state: GraphState):
    print(f"\n 공고 검색중")
    message = state["message"]
    result = await parse_job_search_request(message)

    return {
        "job_search_request": result
    }

async def keyword_job_search_node(state: GraphState):
    print(f"\n 키워드 기반 검색")

    return {
    }

async def profile_job_search_node(state: GraphState):
    print(f"\n 프로필 기반 검색")

    return {
    }


#프로필을 업데이트 하는 노드
async def profile_update_node(state: GraphState):
    print(f"\n 프로필 업데이트")

    return {}

#내 프로필과 공고가 얼마나 적합한지 스코어링하는 노드
async def matching_score(state: GraphState):
    print(f"\n 공고 매칭")

    return {}

async def final_node(state: GraphState):
    print("\n 최종 답변 생성중")

    #augment_llm.invoke()

    return {"response" : "최종 답변입니다."}