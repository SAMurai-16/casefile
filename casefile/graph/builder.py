from typing import Literal
from langgraph.graph import StateGraph, START, END
from ..schema import ClaimState
from ..agents.supervisor import supervisor_node
from ..agents.extractor import extractor_node
from ..agents.investigator import investigator_node
from ..agents.reviewer import reviewer_node
from .human_gate import human_gate_node

def terminate_node(state: ClaimState) -> dict:
    """Terminal sink node that finalizes claim settlement records."""
    return {
        "current_phase": "terminated"
    }

def route_from_supervisor(state: ClaimState) -> Literal["extractor", "investigator", "reviewer", "human_gate", "terminate"]:
    """Deterministic routing function based on state phase."""
    phase = state.get("current_phase", "terminated")
    if phase in ("extraction", "extractor"):
        return "extractor"
    elif phase in ("investigation", "investigator"):
        return "investigator"
    elif phase in ("review", "reviewer"):
        return "reviewer"
    elif phase in ("human_gate", "human"):
        return "human_gate"
    else:
        return "terminate"

def build_claims_graph(checkpointer=None):
    """
    Constructs and compiles the CaseFile Multi-Agent Claims Orchestration Graph.
    """
    builder = StateGraph(ClaimState)
    
    # 1. Register Nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("extractor", extractor_node)
    builder.add_node("investigator", investigator_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("human_gate", human_gate_node)
    builder.add_node("terminate", terminate_node)
    
    # 2. Set Entry Point
    builder.add_edge(START, "supervisor")
    
    # 3. Dynamic Routing from Supervisor
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "extractor": "extractor",
            "investigator": "investigator",
            "reviewer": "reviewer",
            "human_gate": "human_gate",
            "terminate": "terminate"
        }
    )
    
    # 4. Specialist Workers Always Return Control to Supervisor
    builder.add_edge("extractor", "supervisor")
    builder.add_edge("investigator", "supervisor")
    builder.add_edge("reviewer", "supervisor")
    
    # 5. Human Gate Exits to Terminate
    builder.add_edge("human_gate", "terminate")
    builder.add_edge("terminate", END)
    
    # 6. Compile Graph with Checkpointer
    return builder.compile(checkpointer=checkpointer)
