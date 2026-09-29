from typing import Optional, List, Dict, Any, Literal
from typing_extensions import TypedDict
from .decisions import ExtractionResult, InvestigationResult, ReviewResult, HumanDecision
from .handoffs import HandoffPayload

class ClaimState(TypedDict):
    """
    Central state machine context that flows through the LangGraph nodes.
    Checkpointed after every superstep.
    """
    # Claim Identity
    claim_id: str
    run_id: str
    thread_id: str
    
    # Core Raw Documents (Always required)
    fnol_raw: Dict[str, Any]
    estimate_raw: Dict[str, Any]
    policy_raw: Dict[str, Any]
    
    # Optional Auxiliary Raw Documents
    rental_raw: Optional[Dict[str, Any]]
    medical_raw: Optional[Dict[str, Any]]
    third_party_raw: Optional[Dict[str, Any]]
    
    # Typed Specialist Agent Outputs
    extraction: Optional[ExtractionResult]
    investigation: Optional[InvestigationResult]
    review: Optional[ReviewResult]
    human_decision: Optional[HumanDecision]
    
    # State Machine Phase and Control Flow
    current_phase: Literal[
        "intake",
        "extraction",
        "investigation",
        "review",
        "human_gate",
        "terminated"
    ]
    step_count: int
    rework_count: int
    handoff_history: List[HandoffPayload]
    
    # Guard Rails & Resource Budgeting
    total_tokens: int
    total_cost_usd: float
    budget_exceeded: bool
    max_steps_exceeded: bool
    
    # Terminal Settlement State
    terminal_status: Optional[Literal[
        "approved",
        "partial_approved",
        "denied",
        "escalated_siu",
        "budget_terminated",
        "step_limit_terminated",
        "human_rejected"
    ]]
    payout_breakdown: Optional[Dict[str, float]]
    final_payout_amount: Optional[float]
    settlement_summary: Optional[str]
