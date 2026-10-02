from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from ..schema.decisions import ExtractionResult, InvestigationResult, ReviewResult, HumanDecision
from ..schema.handoffs import HandoffPayload

class ClaimListItem(BaseModel):
    claim_id: str
    filing_channel: str = "Standard"
    incident_date: Optional[str] = None
    policyholder_name: Optional[str] = None
    vehicle_summary: Optional[str] = None
    total_claimed: Optional[float] = None
    attached_documents: List[str] = Field(default_factory=list)

class ClaimListResponse(BaseModel):
    claims: List[ClaimListItem]
    total: int

class ClaimDetailResponse(BaseModel):
    claim_id: str
    raw_documents: Dict[str, Any]
    extraction: Optional[ExtractionResult] = None
    investigation: Optional[InvestigationResult] = None
    review: Optional[ReviewResult] = None
    human_decision: Optional[HumanDecision] = None
    status: str = "ready"

class ClaimIngestRequest(BaseModel):
    claim_id: Optional[str] = None
    fnol_raw: Dict[str, Any]
    estimate_raw: Dict[str, Any]
    policy_raw: Dict[str, Any]
    rental_raw: Optional[Dict[str, Any]] = None
    medical_raw: Optional[Dict[str, Any]] = None
    third_party_raw: Optional[Dict[str, Any]] = None

class ClaimIngestResponse(BaseModel):
    claim_id: str
    message: str

class RunClaimRequest(BaseModel):
    auto_approve: bool = False
    thread_id: Optional[str] = None
    model_override: Optional[str] = None

class RunClaimResponse(BaseModel):
    claim_id: str
    run_id: str
    thread_id: str
    status: str
    message: str

class RunStatusResponse(BaseModel):
    claim_id: str
    run_id: str
    thread_id: str
    current_phase: str
    active_node: Optional[str] = None
    step_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    status: str
    is_paused_at_gate: bool = False
    terminal_status: Optional[str] = None
    final_payout_amount: Optional[float] = None
    payout_breakdown: Optional[Dict[str, float]] = None
    settlement_summary: Optional[str] = None

class ApprovalDossierResponse(BaseModel):
    claim_id: str
    thread_id: str
    policyholder_vehicle: str
    repair_shop: str
    
    # Actuarial Risk Profile & Vehicle Valuation
    fraud_risk_score: int
    fraud_risk_level: str
    siu_referral_recommended: bool
    detected_fraud_signals: List[str] = Field(default_factory=list)
    actual_cash_value: float = 0.0
    repair_to_acv_ratio: float = 0.0
    is_total_loss_candidate: bool = False
    
    # Contract Terms & Clause Auditing
    endorsements_validated: List[str] = Field(default_factory=list)
    applied_exclusions: List[str] = Field(default_factory=list)
    clause_audit_notes: List[str] = Field(default_factory=list)
    discrepancy_details: List[str] = Field(default_factory=list)

    # Settlement Payout Breakdown
    itemized_payout_breakdown: Dict[str, float] = Field(default_factory=dict)
    total_proposed_payout: float = 0.0
    policy_collision_limit: float = 0.0
    deductible_applied: float = 0.0
    rental_reimbursement_eligible: float = 0.0
    medical_payments_eligible: float = 0.0
    liability_warning: Optional[str] = None
    recommendation: str = "approve"
    justification: str = ""
    action_required: str = "Please approve, reject, or adjust this multi-line settlement payout."

class HumanDecisionRequest(BaseModel):
    approver_id: str = "senior_claims_adjuster"
    action: Literal["approve", "reject", "rework"] = "approve"
    authorized_amount: Optional[float] = None
    comments: str = "Authorized multi-line coverage settlement."

class HumanDecisionResponse(BaseModel):
    claim_id: str
    thread_id: str
    action: str
    final_payout_authorized: float
    terminal_status: str
    settlement_summary: str
    message: str

class CheckpointSnapshotItem(BaseModel):
    checkpoint_id: str
    step: int
    node: str
    phase: str
    timestamp: str

class ThreadStateResponse(BaseModel):
    thread_id: str
    claim_id: Optional[str] = None
    current_phase: Optional[str] = None
    next_nodes: List[str] = Field(default_factory=list)
    is_interrupted: bool = False
    step_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    values: Dict[str, Any] = Field(default_factory=dict)

class ThreadHistoryResponse(BaseModel):
    thread_id: str
    total_checkpoints: int
    checkpoints: List[CheckpointSnapshotItem]

class ReplayRequest(BaseModel):
    checkpoint_id: Optional[str] = None
    target_phase: Optional[str] = None

class TraceSummaryResponse(BaseModel):
    run_id: str
    claim_id: str
    total_steps: int
    total_tokens: int
    total_cost_usd: float
    execution_path: List[str]
    trace_data: Dict[str, Any]

class AnalyticsSummaryResponse(BaseModel):
    total_claims_in_store: int
    total_runs_executed: int
    total_cost_usd: float
    total_tokens_used: float
    avg_cost_per_claim_usd: float
    terminal_status_breakdown: Dict[str, int]
    avg_fraud_risk_score: float

class SystemHealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    checkpointer_status: str
    database_status: str

class SystemConfigResponse(BaseModel):
    llm_provider: str
    llm_model: str
    max_steps_guard: int
    cost_ceiling_guard_usd: float
    checkpointer_backend: str
    default_rework_limit: int
