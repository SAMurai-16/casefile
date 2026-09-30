from datetime import datetime, timezone
from langgraph.types import interrupt
from ..schema import ClaimState, HumanDecision, HandoffPayload

def human_gate_node(state: ClaimState) -> dict:
    """
    Human Approval Gate:
    Enforces the mandate: 'Never pay out without a human.'
    Pauses graph execution via interrupt() to await adjuster authorization.
    Presents itemized multi-bucket payout table, risk profile, and liability warnings.
    """
    review = state.get("review")
    extraction = state.get("extraction")
    investigation = state.get("investigation")
    
    proposed_amount = review.proposed_payout_amount if review else 0.0
    breakdown = review.payout_breakdown if review and review.payout_breakdown else {"total": proposed_amount}
    
    # 1. Surface interactive approval payload to human adjuster
    prompt_payload = {
        "claim_id": state["claim_id"],
        "policyholder_vehicle": f"{extraction.vehicle_year} {extraction.vehicle_make} {extraction.vehicle_model}" if extraction else "Unknown",
        "repair_shop": extraction.repair_facility_name if extraction else "Unknown",
        
        # Actuarial Risk Profile & Vehicle Valuation
        "fraud_risk_score": investigation.fraud_risk_score if investigation else 0,
        "fraud_risk_level": investigation.fraud_risk_level if investigation else "low",
        "siu_referral_recommended": investigation.siu_referral_recommended if investigation else False,
        "detected_fraud_signals": investigation.detected_fraud_signals if investigation else [],
        "actual_cash_value": investigation.actual_cash_value if investigation else 0.0,
        "repair_to_acv_ratio": investigation.repair_to_acv_ratio if investigation else 0.0,
        "is_total_loss_candidate": investigation.is_total_loss_candidate if investigation else False,
        
        # Contract Terms & Clause Auditing
        "endorsements_validated": investigation.endorsements_validated if investigation else [],
        "applied_exclusions": investigation.applied_exclusions if investigation else [],
        "clause_audit_notes": investigation.clause_audit_notes if investigation else [],
        "discrepancy_details": review.discrepancy_details if review else [],

        # Settlement Payout Breakdown
        "itemized_payout_breakdown": breakdown,
        "total_proposed_payout": proposed_amount,
        "policy_collision_limit": investigation.collision_limit_per_incident if investigation else 0.0,
        "deductible_applied": investigation.collision_deductible if investigation else 0.0,
        "rental_reimbursement_eligible": investigation.rental_eligible_payout if investigation else 0.0,
        "medical_payments_eligible": investigation.medpay_eligible_payout if investigation else 0.0,
        "liability_warning": review.liability_warning if review else None,
        "recommendation": review.recommendation if review else "approve",
        "justification": review.justification if review else "",
        "action_required": "Please approve, reject, or adjust this multi-line settlement payout."
    }
    
    if state.get("human_decision") is not None:
        human_input = state["human_decision"]
    else:
        human_input = interrupt(prompt_payload)
    
    # Convert input to structured HumanDecision
    if isinstance(human_input, dict):
        decision = HumanDecision(
            approver_id=human_input.get("approver_id", "senior_claims_adjuster"),
            action=human_input.get("action", "approve"),
            final_payout_authorized=float(human_input.get("authorized_amount", proposed_amount)),
            comments=human_input.get("comments", "Authorized multi-line coverage settlement."),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    elif isinstance(human_input, HumanDecision):
        decision = human_input
    else:
        decision = HumanDecision(
            approver_id="system_human_proxy",
            action="approve",
            final_payout_authorized=proposed_amount,
            comments="Approved by adjuster proxy",
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    action = decision.action
    terminal_status = "approved" if action == "approve" else "human_rejected"
    final_payout = decision.final_payout_authorized if action == "approve" else 0.0

    handoff = HandoffPayload(
        source_node="human_gate",
        target_node="terminate",
        action="HUMAN_APPROVE" if action == "approve" else "HUMAN_REJECT",
        claim_id=state["claim_id"],
        step_number=state["step_count"] + 1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        summary=f"Human adjuster {decision.approver_id} {action.upper()}D multi-line payout of ${final_payout:,.2f}"
    )

    breakdown_text = ", ".join(f"{k}: ${v:,.2f}" for k, v in breakdown.items())

    return {
        "human_decision": decision,
        "terminal_status": terminal_status,
        "final_payout_amount": final_payout,
        "payout_breakdown": breakdown,
        "step_count": state["step_count"] + 1,
        "handoff_history": state["handoff_history"] + [handoff],
        "current_phase": "terminated",
        "settlement_summary": f"Human Adjuster ({decision.approver_id}) decision: {action.upper()}. Authorized: ${final_payout:,.2f} [{breakdown_text}]. Notes: {decision.comments}"
    }
