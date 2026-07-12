from langgraph.graph import END, START, StateGraph

from llm import get_llm
from state import GraphState
from nodes import *

def route_by_intent(state: GraphState):
    return state["intent"]

workflow = StateGraph(GraphState)

#노드 추가
workflow.add_node("route_intent_node", route_intent_node)
workflow.add_node("search_job_node",search_job_node)
workflow.add_node("profile_update_node",profile_update_node)
workflow.add_node("matching_score_node",matching_score)
workflow.add_node("final_node",final_node)

#엣지 추가
workflow.add_edge(START, "route_intent_node")
workflow.add_edge("search_job_node", "final_node")
workflow.add_edge("profile_update_node", "final_node")
workflow.add_edge("matching_score_node", "final_node")
workflow.add_edge("final_node", END)

#컨디셔널 엣지 추가
workflow.add_conditional_edges(
    "route_intent_node",
    route_by_intent,
    {
        "search_job":"search_job_node", 
        "profile_update":"profile_update_node",
        "matching_score":"matching_score_node"
    }
)

graph = workflow.compile()