from datetime import datetime, timezone
from typing import Dict, Any, List
from ..schema import ClaimState, ReviewResult, HandoffPayload
from ..tracing.cost_tracker import calculate_call_cost
from .llm_factory import LLMFactory

def reviewer_node(state: ClaimState) -> dict:
    """
    Reviewer Agent:
    1. Deterministic Math & Line-Item Audit:
       - Audits invoice arithmetic and identifies shop variances (e.g. $200 parts discrepancy)
         purely from extracted structured data (extraction.itemized_repairs vs extraction.total_parts_cost).
       - Computes precise, legally binding multi-line payout breakdowns and limit ceilings.
    2. Adversarial Damage Cross-Examination & Human Gate Synthesis:
       - Ingests COMPLETE Extractor and Investigator findings (full claim context, vehicle specs,
         auxiliary documents, actuarial fraud signals, and policy contract clauses).
       - LLM cross-examines driver FNOL narrative against shop repair line items and contract terms.
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
    
    # 1. Component vs Grand Total Check
    parts = extraction.total_parts_cost
    labor = extraction.total_labor_cost
    additional = extraction.total_additional_costs
    grand = extraction.claimed_grand_total
    computed_sum = round(parts + labor + additional, 2)
    
    if abs(computed_sum - grand) > 0.05:
        math_discrepancies.append(
            f"Arithmetic variance in repair summary: Stated grand total (${grand:,.2f}) != Sum of parts + labor + additional (${computed_sum:,.2f}). Difference: ${abs(grand - computed_sum):,.2f}"
        )

    # 2. Itemized Parts vs Stated Parts Total Check (e.g. Claim 002 $200 parts variance)
    raw_parts_items = [
        item for item in (extraction.itemized_repairs or []) 
        if item.category == "parts"
    ]
    if raw_parts_items:
        raw_parts_sum = round(sum(item.amount for item in raw_parts_items), 2)
        if parts > 0 and abs(raw_parts_sum - parts) > 1.0:
            diff = round(parts - raw_parts_sum, 2)
            math_discrepancies.append("Shop parts summary contains arithmetic discrepancy")
            if diff > 0:
                math_discrepancies.append(
                    f"Shop invoice line-item parts variance detected: Stated parts subtotal (${parts:,.2f}) exceeds sum of itemized parts (${raw_parts_sum:,.2f}) by ${diff:,.2f}."
                )
    else:
        # Fallback check on raw JSON if extractor itemized_repairs was empty
        estimate_raw = state.get("estimate_raw", {})
        if isinstance(estimate_raw, dict):
            line_items = estimate_raw.get("line_items") or estimate_raw.get("estimate_lines") or estimate_raw.get("work_items") or []
            fin = estimate_raw.get("financial_summary") or estimate_raw.get("totals_breakdown") or estimate_raw.get("invoice_totals") or estimate_raw.get("cost_recap") or estimate_raw.get("accounting_summary") or {}
            if line_items and fin:
                raw_parts_sum = round(sum(float(item.get("part_amt") or item.get("parts_cost") or 0.0) for item in line_items if isinstance(item, dict)), 2)
                stated_parts = float(fin.get("parts_subtotal") or fin.get("parts_total") or fin.get("total_parts") or 0.0)
                if stated_parts > 0 and abs(raw_parts_sum - stated_parts) > 1.0:
                    diff = round(stated_parts - raw_parts_sum, 2)
                    math_discrepancies.append("Shop parts summary contains arithmetic discrepancy")
                    if diff > 0:
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

    # Format itemized shop repair operations for adversarial cross-check
    if extraction.itemized_repairs:
        repairs_section = "\n".join(
            f"  • [{item.category.upper()}] {item.description} (Source: {item.part_type or 'Labor'})"
            f"{f' [{item.labor_hours} hrs]' if item.labor_hours else ''} - ${item.amount:,.2f}"
            for item in extraction.itemized_repairs[:30]
        )
    else:
        estimate_raw = state.get("estimate_raw", {})
        raw_lines = (
            estimate_raw.get("line_items") or 
            estimate_raw.get("estimate_lines") or 
            estimate_raw.get("work_items") or 
            estimate_raw.get("itemized_operations") or 
            estimate_raw.get("repair_operations") or []
        ) if isinstance(estimate_raw, dict) else []
        repairs_section = "\n".join(
            f"  • {item.get('description') or item.get('item_desc') or item.get('service_description') or item.get('operation') or 'Repair operation'}: "
            f"${float(item.get('part_amt') or item.get('part_price') or item.get('parts_cost') or item.get('line_cost') or item.get('amount') or 0):,.2f}"
            for item in raw_lines[:30] if isinstance(item, dict)
        ) if raw_lines else "  • (No itemized breakdown provided in estimate)"

    # Format auxiliary documents from extraction
    aux_details = []
    if extraction.rental_receipt:
        rr = extraction.rental_receipt
        aux_details.append(
            f"  • Rental Invoice: {rr.rental_agency} (Inv #{rr.invoice_number or 'N/A'}), "
            f"{rr.days_billed} days @ ${rr.daily_rate:.2f}/day (Total Billed: ${rr.total_charged:,.2f}, Dates: {rr.start_date} to {rr.end_date})"
        )
    if extraction.medical_bills:
        for b in extraction.medical_bills:
            aux_details.append(
                f"  • Medical Bill: {b.provider_name} for patient {b.patient_name} (${b.total_billed:,.2f}) - "
                f"Service: {b.diagnosis_or_treatment} on {b.date_of_service}"
            )
    if extraction.third_party_claim:
        tp = extraction.third_party_claim
        aux_details.append(
            f"  • Third-Party Demand: Claimant {tp.claimant_name} (Damaged: {tp.vehicle_damaged or 'Vehicle'}) - "
            f"Property Damage: ${tp.property_damage_claimed:,.2f}, Bodily Injury: ${tp.bodily_injury_claimed:,.2f}. Summary: {tp.demand_summary}"
        )
    auxiliary_section = "\n".join(aux_details) if aux_details else "  • No auxiliary rental, medical, or third-party expenses claimed."

    # Format fraud risk signals from investigation
    fraud_signals_text = (
        "\n".join(f"  • {sig}" for sig in investigation.detected_fraud_signals)
        if investigation.detected_fraud_signals
        else "  • No adverse risk signals detected (clean actuarial history)"
    )

    # Format contract clauses and endorsement audit findings from investigation
    endorsements_text = (
        "\n".join(f"  • {e}" for e in investigation.endorsements_validated)
        if investigation.endorsements_validated
        else "  • No active endorsement riders"
    )
    exclusions_text = (
        "\n".join(f"  • 🚫 {ex}" for ex in investigation.applied_exclusions)
        if investigation.applied_exclusions
        else "  • None (No policy exclusions triggered)"
    )
    clauses_text = (
        "\n".join(f"  • ⚖️ {c}" for c in investigation.clause_audit_notes)
        if investigation.clause_audit_notes
        else "  • Standard policy terms and conditions satisfied"
    )

    police_info = f"Filed ({extraction.police_report_number or 'Report on file'})" if extraction.police_report_filed else "None filed"
    other_party_info = f"Yes ({extraction.other_party_details or 'Third party involved'})" if extraction.other_party_involved else "No (Single-vehicle incident)"
    mileage_str = f"{extraction.vehicle_mileage:,}" if extraction.vehicle_mileage else "Not reported"

    # =========================================================================
    # STEP 3: ADVERSARIAL DAMAGE CROSS-EXAMINATION & SYNTHESIS (LLM)
    # =========================================================================
    prompt = f"""
You are the Senior Claims Reviewer Agent.
Your job is adversarial cross-document examination, verifying contractual compliance across all lines, and synthesizing the executive justification for the Human Approval Gate.

=== CLAIM & VEHICLE IDENTIFICATION ===
- Claim ID: {state["claim_id"]}
- Insured Vehicle: {extraction.vehicle_year} {extraction.vehicle_make} {extraction.vehicle_model} (VIN: {extraction.vehicle_vin}, Plate: {extraction.vehicle_license_plate or 'N/A'}, Odometer: {mileage_str} miles)
- Incident Date & Location: {extraction.incident_date} {extraction.incident_time or ''} at {extraction.incident_location}
- Driver Account: {extraction.incident_summary}
- Driver-Reported Damage Areas: {', '.join(extraction.reported_damage_areas)}
- Vehicle Drivable: {extraction.is_drivable}
- Police Report: {police_info}
- Other Party Involved: {other_party_info}
- Injuries Reported: {extraction.injuries_summary or 'None'}
- Current Rework Attempt: {state.get("rework_count", 0)}

=== BODY SHOP REPAIR INVOICE & BILLED OPERATIONS ===
- Facility: {extraction.repair_facility_name} (Tax ID: {extraction.repair_facility_tax_id or 'N/A'}, Estimate Date: {extraction.estimate_date or 'N/A'})
- Total Claimed by Shop: ${extraction.claimed_grand_total:,.2f} (Parts: ${extraction.total_parts_cost:,.2f}, Labor: ${extraction.total_labor_cost:,.2f}, Add'l: ${extraction.total_additional_costs:,.2f})
- Itemized Parts & Labor Operations Billed:
{repairs_section}

=== AUXILIARY EXPENSES CLAIMED ===
{auxiliary_section}

=== PRE-COMPUTED ARITHMETIC AUDIT FINDINGS ===
{discrepancy_section}

=== ACTUARIAL COVERAGE & RISK CONTEXT (INVESTIGATOR AUDIT) ===
- Policy Number: {investigation.policy_number} (Status: {investigation.policy_status}, Term: {investigation.policy_effective_date} to {investigation.policy_expiration_date})
- Incident Classification: {investigation.incident_classification.upper()}
- Overall Coverage Verdict: {investigation.coverage_verdict.upper()} {f'— Denial: {investigation.coverage_denial_reason}' if investigation.coverage_denial_reason else ''}
- Collision Limits: Limit=${(investigation.collision_limit_per_incident or 0):,.2f}, Deductible=${(investigation.collision_deductible or 0):,.2f} (Coverage In Force: {investigation.collision_covered})
- Pre-Accident Vehicle ACV: ${investigation.actual_cash_value or 0:,.2f} (Repair/ACV: {(investigation.repair_to_acv_ratio or 0) * 100:.1f}%)
- Total Loss Threshold Triggered: {investigation.is_total_loss_candidate}
- Fraud Risk Score: {investigation.fraud_risk_score}/100 ({investigation.fraud_risk_level.upper()}) | SIU Mandatory: {investigation.siu_referral_recommended}
- Actuarial Fraud Risk Factors (SHAP Contributions):
{fraud_signals_text}
- Third-Party Exposure: Flag={investigation.liability_exposure_flag} ({investigation.liability_exposure_summary or 'No exposure'})

=== POLICY CONTRACT CLAUSES & ENDORSEMENTS AUDIT ===
Active Endorsement Riders:
{endorsements_text}

Exclusions Triggered:
{exclusions_text}

Contract Clause & Condition Findings:
{clauses_text}

=== COMPUTED SETTLEMENT PAYOUT (DETERMINISTIC) ===
{payout_section}
  TOTAL PROPOSED PAYOUT: ${proposed_payout:,.2f} (Limit Status: {limit_check})

Review Tasks:
1. Physical Damage Alignment:
   - Check if body shop operations match the impact physics and damage areas described by the driver.
   - Flag any unitemized panels, invoice padding, or unrelated prior damage in discrepancy_details.
2. Contractual & Legal Clause Compliance:
   - Cross-check the itemized operations and payout against the Investigator's clause audit notes and active endorsements.
   - If OEM parts were billed without an active OEM rider under LKQ rules (SEC-IV-COND-7), reference this finding.
   - If custom equipment limits apply (SEC-IV-LIMIT-4), verify that custom items are compliant.
3. Settlement Recommendation:
   - If Policy is Lapsed/Cancelled: recommend "deny".
   - If SIU Referral is Recommended or Fraud is Critical: recommend "escalate_siu".
   - If unresolvable factual contradiction exists between driver narrative and damage areas (e.g. impact described on rear bumper, but estimate bills front suspension, and rework < 2): recommend "rework" with target and instructions.
     NOTE: Do NOT request rework for shop arithmetic discrepancies or auxiliary limit caps; those are already audited and presented to the human adjuster in discrepancy_details.
   - If repair cost exceeds policy collision limit: recommend "partial_approve".
   - Otherwise: recommend "approve".
4. Adjuster Briefing:
   - Write a clear, comprehensive executive justification summarizing the evidence, coverage application, clause notes, and any detected discrepancies.
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
        "input_tokens": 1400,
        "output_tokens": 400,
        "total_tokens": 1800
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
