from typing import Literal, Any, Dict
from pydantic import BaseModel, Field

NodeName = Literal[
    "supervisor",
    "extractor",
    "investigator",
    "reviewer",
    "human_gate",
    "terminate",
]

ActionType = Literal[
    "EXTRACT",
    "INVESTIGATE",
    "REVIEW",
    "REWORK",
    "APPROVE",
    "PARTIAL_APPROVE",
    "DENY",
    "ESCALATE_SIU",
    "HUMAN_APPROVE",
    "HUMAN_REJECT",
    "BUDGET_EXCEEDED",
    "MAX_STEPS_EXCEEDED",
]

class HandoffPayload(BaseModel):
    """
    Strict typed contract for any transition between nodes in the graph.
    Free-text string handoffs are explicitly prohibited.
    """
    source_node: NodeName
    target_node: NodeName
    action: ActionType
    claim_id: str
    step_number: int
    timestamp: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(description="Deterministic machine-readable summary of the handoff reason")
