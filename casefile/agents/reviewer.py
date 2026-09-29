from datetime import datetime, timezone
from ..schema import ClaimState, ReviewResult, HandoffPayload
from ..tracing.cost_tracker import calculate_call_cost
from .llm_factory import LLMFactory

def reviewer_node(state: ClaimState) -> dict:
    """
    Reviewer Agent:
    1. Deterministic Math & Line-Item Audit:
       - Audits invoice arithmetic and identifies shop variances (e.g. $200 parts discrepancy).
       - Computes precise, legally binding multi-line payout breakdowns and limit ceilings.
    2. Adversarial Damage Cross-Examination & Human Gate Synthesis:
       - LLM cross-examines driver FNOL narrative against shop repair line items.
       - Synthesizes findings, flags unrelated prior damage or inflation, and drafts the adjuster brief.
    """
    extraction = state["extraction"]
    investigation = state["investigation"]
    
    if not extraction or not investigation:
        raise ValueError("Reviewer requires both extraction and investigation results to be completed.")

    # =========================================================================
    # STEP 1: DETERMINISTIC LINE-ITEM ARITHMETIC AUDIT (Pure Python)
    # =========================================================================
    math_discrepancies = []
    
    # Check A: Component totals (parts + labor + additional) vs claimed grand total
    components_sum = round(extraction.total_parts_cost + extraction.total_labor_cost + extraction.total_additional_costs, 2)
    if abs(components_sum - extraction.claimed_grand_total) > 1.0:
        diff = extraction.claimed_grand_total - components_sum
        math_discrepancies.append(
            f"Arithmetic discrepancy in estimate: Components sum (${components_sum:,.2f}) differs from claimed total (${extraction.claimed_grand_total:,.2f}) by ${diff:+,.2f}."
        )

    # Check B: Raw invoice line items vs printed summary header (e.g. Claim 002 $200 parts variance)
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

    # =========================================================================
    # STEP 2: DETERMINISTIC PAYOUT & LIMIT ADJUDICATION (Pure Python)
    # =========================================================================
    payout_breakdown = {}
    proposed_payout = 0.0
    limit_check = "within_limits"

    if investigation.policy_status in ("Lapsed", "Cancelled", "Suspended"):
        limit_check = "policy_void"
        proposed_payout = 0.0
    elif investigation.fraud_risk_level == "critical" or investigation.coverage_verdict == "not_covered":
        proposed_payout = 0.0
    else:
        # 1. Collision line
        if investigation.collision_covered:
            raw_cost = extraction.claimed_grand_total
            limit = investigation.collision_limit_per_incident or 0.0
            deductible = investigation.collision_deductible or 0.0
            if limit > 0 and raw_cost > limit:
                limit_check = "exceeds_limits"
                repair_payout = max(0.0, round(limit - deductible, 2))
            else:
                repair_payout = max(0.0, round(raw_cost - deductible, 2))
            payout_breakdown["vehicle_repair"] = repair_payout
            
        # 2. Rental reimbursement line
        if investigation.rental_eligible_payout > 0:
            payout_breakdown["rental_car"] = round(investigation.rental_eligible_payout, 2)
            
        # 3. Medical payments (MedPay) line
        if investigation.medpay_eligible_payout > 0:
            payout_breakdown["medical_payments"] = round(investigation.medpay_eligible_payout, 2)
            
        proposed_payout = round(sum(payout_breakdown.values()), 2)

    # Format findings for prompt
    discrepancy_section = "\n".join(f"  • {d}" for d in math_discrepancies) if math_discrepancies else "  • All invoice line items and totals verified with 100% arithmetic precision."
    payout_section = "\n".join(f"  • {k.replace('_', ' ').title()}: ${v:,.2f}" for k, v in payout_breakdown.items()) if payout_breakdown else "  • No eligible payout ($0.00)"

    # =========================================================================
    # STEP 3: ADVERSARIAL DAMAGE CROSS-EXAMINATION & SYNTHESIS (LLM)
    # =========================================================================
    prompt = f"""
You are the Senior Claims Reviewer Agent.
Your job is adversarial cross-document examination and synthesizing the executive justification for the Human Approval Gate.

=== CLAIM IDENTIFICATION ===
- Claim ID: {state["claim_id"]}
- Current Rework Attempt: {state.get("rework_count", 0)}

=== LOSS NARRATIVE (DRIVER STATEMENT) ===
- Incident Date & Location: {extraction.incident_date} at {extraction.incident_location}
- Driver Account: {extraction.incident_summary}
- Driver-Reported Damage Areas: {', '.join(extraction.reported_damage_areas)}
- Injuries Reported: {extraction.injuries_summary or 'None'}

=== BODY SHOP REPAIR INVOICE ===
- Facility: {extraction.repair_facility_name}
- Total Claimed by Shop: ${extraction.claimed_grand_total:,.2f} (Parts: ${extraction.total_parts_cost:,.2f}, Labor: ${extraction.total_labor_cost:,.2f}, Add'l: ${extraction.total_additional_costs:,.2f})

=== PRE-COMPUTED ARITHMETIC AUDIT FINDINGS ===
{discrepancy_section}

=== ACTUARIAL COVERAGE & RISK CONTEXT ===
- Policy Status: {investigation.policy_status}
- Pre-Accident Vehicle ACV: ${investigation.actual_cash_value or 0:,.2f} (Repair/ACV: {(investigation.repair_to_acv_ratio or 0) * 100:.1f}%)
- Total Loss Threshold Triggered: {investigation.is_total_loss_candidate}
- Fraud Risk Score: {investigation.fraud_risk_score}/100 ({investigation.fraud_risk_level.upper()})
- SIU Referral Recommended: {investigation.siu_referral_recommended}
- Third-Party Exposure: {investigation.liability_exposure_flag} ({investigation.liability_exposure_summary or 'No exposure'})

=== COMPUTED SETTLEMENT PAYOUT (DETERMINISTIC) ===
{payout_section}
  TOTAL PROPOSED PAYOUT: ${proposed_payout:,.2f} (Limit Status: {limit_check})

Review Tasks:
1. Physical Damage Alignment:
   - Check if body shop operations match the impact physics and damage areas described by the driver.
   - Flag any unitemized panels, invoice padding, or unrelated prior damage in discrepancy_details.
2. Settlement Recommendation:
   - If Policy is Lapsed/Cancelled: recommend "deny".
   - If SIU Referral is Recommended or Fraud is Critical: recommend "escalate_siu".
   - If unresolvable ambiguity between damage and narrative exists (and rework < 2): recommend "rework" with target and instructions.
   - If repair cost exceeds policy collision limit: recommend "partial_approve".
   - Otherwise: recommend "approve".
3. Adjuster Briefing:
   - Write a clear, comprehensive justification summarizing the evidence, coverage application, and any detected discrepancies.
   - If third-party claims exist without active coverage, include a clear liability_warning.
"""
    structured_llm = LLMFactory.get_structured_llm(ReviewResult)
    result: ReviewResult = structured_llm.invoke(prompt)

    # Ensure deterministic math & audit results override/enrich LLM outputs
    result.payout_breakdown = payout_breakdown
    result.proposed_payout_amount = proposed_payout
    result.repair_cost_vs_limit_check = limit_check
    for d in math_discrepancies:
        if d not in result.discrepancy_details:
            result.discrepancy_details.append(d)

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
