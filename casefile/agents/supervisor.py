from datetime import datetime, timezone
from ..schema import ClaimState, HandoffPayload
from ..config import MAX_STEPS, MAX_REWORK_COUNT, COST_CEILING_USD, TOKEN_CEILING

def supervisor_node(state: ClaimState) -> dict:
    """
    Supervisor Node:
    Purely deterministic routing logic. No non-deterministic prompt calls.
    Enforces loop guards, token/dollar budgets, and sequential agent handoffs.
    """
    step = state["step_count"] + 1
    now = datetime.now(timezone.utc).isoformat()
    
    # 1. Guard: Check Budget Ceilings
    if state["total_cost_usd"] >= COST_CEILING_USD or state["total_tokens"] >= TOKEN_CEILING:
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="terminate",
            action="BUDGET_EXCEEDED",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary=f"Cost ceiling breached (${state['total_cost_usd']:.4f} >= ${COST_CEILING_USD:.2f}). Terminating run."
        )
        return {
            "current_phase": "terminated",
            "terminal_status": "budget_terminated",
            "budget_exceeded": True,
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff],
            "settlement_summary": "Graph halted: Claim processing budget ceiling reached."
        }

    # 2. Guard: Check Max Steps Loop Limit
    if state["step_count"] >= MAX_STEPS:
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="terminate",
            action="MAX_STEPS_EXCEEDED",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary=f"Max execution steps hit ({state['step_count']} >= {MAX_STEPS}). Terminating run."
        )
        return {
            "current_phase": "terminated",
            "terminal_status": "step_limit_terminated",
            "max_steps_exceeded": True,
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff],
            "settlement_summary": "Graph halted: Maximum step limit reached to prevent infinite recursion."
        }

    # 3. Deterministic Pipeline Routing
    
    # Phase A: Need Extraction?
    if state["extraction"] is None:
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="extractor",
            action="EXTRACT",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary="Dispatching raw claim documents to Extractor Agent."
        )
        return {
            "current_phase": "extraction",
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff]
        }

    # Phase B: Need Investigation?
    if state["investigation"] is None:
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="investigator",
            action="INVESTIGATE",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary="Dispatching policy record and loss context to Investigator Agent."
        )
        return {
            "current_phase": "investigation",
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff]
        }

    # Phase C: Fast Short-Circuit for Cancelled / Lapsed / Inactive Policy
    if state["investigation"].policy_status in ["Lapsed", "Cancelled", "Suspended"] or state["investigation"].coverage_verdict == "not_covered":
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="terminate",
            action="DENY",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary="Fast-path denial: Policy inactive at date of loss."
        )
        return {
            "current_phase": "terminated",
            "terminal_status": "denied",
            "final_payout_amount": 0.0,
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff],
            "settlement_summary": f"Claim denied: {state['investigation'].coverage_denial_reason or 'Policy inactive'}"
        }

    # Phase D: Need Review?
    if state["review"] is None:
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="reviewer",
            action="REVIEW",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary="Dispatching normalized evidence to Reviewer Agent for cross-check."
        )
        return {
            "current_phase": "review",
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff]
        }

    # Phase E: Handle Reviewer Rework Loop Guard
    if state["review"].recommendation == "rework":
        if state["rework_count"] < MAX_REWORK_COUNT:
            target = state["review"].rework_target or "extractor"
            handoff = HandoffPayload(
                source_node="supervisor",
                target_node=target,
                action="REWORK",
                claim_id=state["claim_id"],
                step_number=step,
                timestamp=now,
                summary=f"Reviewer requested rework ({state['rework_count'] + 1}/{MAX_REWORK_COUNT}). Routing back to {target}."
            )
            # Reset the appropriate downstream result for fresh pass
            reset_fields = {"extraction": None, "review": None} if target == "extractor" else {"investigation": None, "review": None}
            target_phase = "extraction" if target == "extractor" else "investigation"
            return {
                **reset_fields,
                "current_phase": target_phase,
                "rework_count": state["rework_count"] + 1,
                "step_count": step,
                "handoff_history": state["handoff_history"] + [handoff]
            }
        else:
            # Rework ceiling exhausted: force escalate to human
            pass

    # Phase F: Route to Human Approval Gate for Payouts, or Terminate for Denials/SIU
    rec = state["review"].recommendation
    
    if rec in ["approve", "partial_approve"]:
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="human_gate",
            action="APPROVE" if rec == "approve" else "PARTIAL_APPROVE",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary=f"Payout recommendation requires human authorization (${state['review'].proposed_payout_amount:,.2f})."
        )
        return {
            "current_phase": "human_gate",
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff]
        }
        
    elif rec == "escalate_siu":
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="terminate",
            action="ESCALATE_SIU",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary="Claim escalated to Special Investigation Unit (SIU) due to critical fraud risk."
        )
        return {
            "current_phase": "terminated",
            "terminal_status": "escalated_siu",
            "final_payout_amount": 0.0,
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff],
            "settlement_summary": "Claim flagged and escalated to SIU. Payout blocked."
        }
        
    elif rec == "deny":
        handoff = HandoffPayload(
            source_node="supervisor",
            target_node="terminate",
            action="DENY",
            claim_id=state["claim_id"],
            step_number=step,
            timestamp=now,
            summary=f"Reviewer concluded claim denial: {state['review'].justification}"
        )
        return {
            "current_phase": "terminated",
            "terminal_status": "denied",
            "final_payout_amount": 0.0,
            "step_count": step,
            "handoff_history": state["handoff_history"] + [handoff],
            "settlement_summary": state["review"].justification
        }
        
    # Default fallback
    return {
        "current_phase": "terminated",
        "terminal_status": "denied",
        "step_count": step,
        "settlement_summary": "Processing concluded."
    }
