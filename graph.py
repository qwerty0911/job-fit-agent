from langgraph.graph import END, START, StateGraph

from nodes import (
    final_node,
    job_search,
    matching_score,
    route_intent_node,
)
from state import GraphState


def route_by_intent(state: GraphState):
    return state["intent"]


workflow = StateGraph(GraphState)

workflow.add_node("route_intent_node", route_intent_node)
workflow.add_node("job_search_node", job_search)
workflow.add_node("matching_score_node", matching_score)
workflow.add_node("final_node", final_node)

workflow.add_edge(START, "route_intent_node")
workflow.add_edge("job_search_node", "final_node")
workflow.add_edge("matching_score_node", "final_node")
workflow.add_edge("final_node", END)

workflow.add_conditional_edges(
    "route_intent_node",
    route_by_intent,
    {
        "search_job": "job_search_node",
        "matching_score": "matching_score_node",
        "others": "final_node",
    },
)

graph = workflow.compile()
