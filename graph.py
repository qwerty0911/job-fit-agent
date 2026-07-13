from langgraph.graph import END, START, StateGraph

from llm import get_llm
from state import GraphState
from nodes import *

#라우팅 함수
def route_by_intent(state: GraphState):
    return state["intent"]

def route_job_search(state: GraphState):
    request = state["job_search_request"]

    if request.mode == "keyword_based":
        return "keyword_job_search"

    return "profile_job_search"

workflow = StateGraph(GraphState)

#노드 추가
workflow.add_node("route_intent_node", route_intent_node)

workflow.add_node("parse_job_search_request_node",parse_job_search_request_node)
workflow.add_node("keyword_job_search_node",keyword_job_search_node)
workflow.add_node("profile_job_search_node",profile_job_search_node)

workflow.add_node("profile_update_node",profile_update_node)
workflow.add_node("matching_score_node",matching_score)
workflow.add_node("final_node",final_node)

#엣지 추가
workflow.add_edge(START, "route_intent_node")
workflow.add_edge("keyword_job_search_node", "final_node")
workflow.add_edge("profile_job_search_node", "final_node")
workflow.add_edge("profile_update_node", "final_node")
workflow.add_edge("matching_score_node", "final_node")
workflow.add_edge("final_node", END)

#컨디셔널 엣지 추가
workflow.add_conditional_edges(
    "route_intent_node",
    route_by_intent,
    {
        "search_job":"parse_job_search_request_node", 
        "profile_update":"profile_update_node",
        "matching_score":"matching_score_node"
    }
)

workflow.add_conditional_edges(
    "parse_job_search_request_node",
    route_job_search,
    {
        "keyword_job_search":"keyword_job_search_node", 
        "profile_job_search":"profile_job_search_node",
    }
)

graph = workflow.compile()