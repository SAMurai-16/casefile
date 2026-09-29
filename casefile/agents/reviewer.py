from datetime import datetime, timezone
from ..schema import ClaimState, ReviewResult, HandoffPayload
from ..tracing.cost_tracker import calculate_call_cost
from .llm_factory import LLMFactory

def reviewer_node(state: ClaimState) -> dict:
    """
    Reviewer Agent:
    Cross-checks all extracted evidence against multi-line coverage investigation findings.
    Synthesizes itemized payout breakdown across all approved coverage buckets.
    """
    extraction = state["extraction"]
    investigation = state["investigation"]
    
    if not extraction or not investigation:
        raise ValueError("Reviewer requires both extraction and investigation results to be completed.")

    prompt = f"""
You are the Claims Reviewer Agent.
Compare the normalized damage extraction with the coverage investigation to reach a final multi-line settlement recommendation.

=== EXTRACTION FINDINGS ===
- Claim ID: {state["claim_id"]}
- Current Rework Attempt: {state.get("rework_count", 0)}
- Incident: {extraction.incident_summary} ({extraction.incident_date} at {extraction.incident_location})
- Vehicle: {extraction.vehicle_year} {extraction.vehicle_make} {extraction.vehicle_model} (VIN: {extraction.vehicle_vin})
- Reported Damage Areas: {', '.join(extraction.reported_damage_areas)}
- Body Shop Repair Total: ${extraction.claimed_grand_total:,.2f} at {extraction.repair_facility_name}
- Rental Claimed: {f"{extraction.rental_receipt.days_billed}d @ ${extraction.rental_receipt.daily_rate}/d (${extraction.rental_receipt.total_charged:,.2f})" if extraction.rental_receipt else "None"}
- Medical Bills Claimed: {f"${sum(b.total_billed for b in extraction.medical_bills):,.2f}" if extraction.medical_bills else "None"}
- Third-Party Claim: {f"${extraction.third_party_claim.property_damage_claimed + extraction.third_party_claim.bodily_injury_claimed:,.2f}" if extraction.third_party_claim else "None"}

=== INVESTIGATION COVERAGE FINDINGS ===
- Policy Status: {investigation.policy_status}
- Incident Classification: {investigation.incident_classification}
- Collision Covered: {investigation.collision_covered} (Limit: ${investigation.collision_limit_per_incident or 0:,.2f}, Deductible: ${investigation.collision_deductible or 0:,.2f})
- Max Eligible Collision Payout: ${investigation.max_eligible_collision_payout or 0:,.2f}
- Rental Eligible Payout: ${investigation.rental_eligible_payout:,.2f} (Notes: {investigation.rental_notes or 'N/A'})
- MedPay Eligible Payout: ${investigation.medpay_eligible_payout:,.2f} (Notes: {investigation.medpay_notes or 'N/A'})
- Liability Exposure Flag: {investigation.liability_exposure_flag} ({investigation.liability_exposure_summary or 'No exposure'})
- Fraud Risk Level: {investigation.fraud_risk_level.upper()} (Score: {investigation.fraud_risk_score}/100)
- SIU Referral Recommended: {investigation.siu_referral_recommended}

Adjudication & Settlement Rules:
1. If Policy Status is Lapsed or Cancelled:
   - Recommend DENY with $0 total payout.
   - If third-party claims exist, issue a critical liability_warning that policyholder faces full personal exposure.
2. If Fraud Risk is CRITICAL:
   - Recommend ESCALATE_SIU with $0 payout pending SIU investigation.
3. If Policy is Active:
   - Calculate itemized payout_breakdown dictionary:
     * "vehicle_repair": min(repair_cost, collision_limit) - deductible (if collision covered)
     * "rental_car": rental_eligible_payout (if rental covered and claimed)
     * "medical_payments": medpay_eligible_payout (if MedPay covered and claimed)
   - Set proposed_payout_amount to the exact sum of all items in payout_breakdown.
   - If repair cost exceeded policy collision limit, recommendation is "partial_approve", otherwise "approve".
4. If there is severe unexplained ambiguity between estimate parts and narrative and rework_count < 2:
   - Recommend REWORK.
"""
    structured_llm = LLMFactory.get_structured_llm(ReviewResult)
    result: ReviewResult = structured_llm.invoke(prompt)

    # Deterministic Line-Item Arithmetic Audit
    math_discrepancies = []
    components_sum = round(extraction.total_parts_cost + extraction.total_labor_cost + extraction.total_additional_costs, 2)
    if abs(components_sum - extraction.claimed_grand_total) > 1.0:
        diff = extraction.claimed_grand_total - components_sum
        math_discrepancies.append(
            f"Arithmetic discrepancy in estimate: Components sum (${components_sum:,.2f}) differs from claimed total (${extraction.claimed_grand_total:,.2f}) by ${diff:+,.2f}."
        )

    estimate_raw = state.get("estimate_raw", {})
    if isinstance(estimate_raw, dict):
        line_items = estimate_raw.get("line_items") or estimate_raw.get("estimate_lines") or estimate_raw.get("work_items") or []
        fin = estimate_raw.get("financial_summary") or estimate_raw.get("totals_breakdown") or estimate_raw.get("invoice_totals") or estimate_raw.get("cost_recap") or estimate_raw.get("accounting_summary") or {}
        if line_items and fin:
            raw_parts_sum = round(sum(float(item.get("part_amt") or item.get("parts_cost") or 0.0) for item in line_items if isinstance(item, dict)), 2)
            stated_parts = float(fin.get("parts_subtotal") or fin.get("parts_total") or fin.get("total_parts") or 0.0)
            if stated_parts > 0 and abs(raw_parts_sum - stated_parts) > 1.0:
                diff = stated_parts - raw_parts_sum
                math_discrepancies.append(
                    f"Shop invoice line-item parts variance detected: Stated parts subtotal (${stated_parts:,.2f}) exceeds sum of itemized parts (${raw_parts_sum:,.2f}) by ${diff:,.2f}."
                )

    for disc in math_discrepancies:
        if disc not in result.discrepancy_details:
            result.discrepancy_details.append(disc)

    tokens_used, cost_usd = calculate_call_cost({
        "input_tokens": 1200,
        "output_tokens": 350,
        "total_tokens": 1550
    })
    
    action_map = {
        "approve": "APPROVE",
        "partial_approve": "PARTIAL_APPROVE",
        "deny": "DENY",
        "escalate_siu": "ESCALATE_SIU",
        "rework": "REWORK"
    }
    
    breakdown_str = ", ".join(f"{k}: ${v:,.2f}" for k, v in result.payout_breakdown.items()) if result.payout_breakdown else f"${result.proposed_payout_amount:,.2f}"
    
    handoff = HandoffPayload(
        source_node="reviewer",
        target_node="supervisor",
        action=action_map.get(result.recommendation, "REVIEW"),
        claim_id=state["claim_id"],
        step_number=state["step_count"] + 1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        summary=f"Recommendation: {result.recommendation.upper()} | Authorized: ${result.proposed_payout_amount:,.2f} [{breakdown_str}]"
    )
    
    return {
        "review": result,
        "payout_breakdown": result.payout_breakdown,
        "step_count": state["step_count"] + 1,
        "total_tokens": state["total_tokens"] + tokens_used,
        "total_cost_usd": state["total_cost_usd"] + cost_usd,
        "handoff_history": state["handoff_history"] + [handoff],
        "current_phase": "review"
    }
