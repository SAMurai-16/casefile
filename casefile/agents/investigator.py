import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from ..schema import ClaimState, InvestigationResult, HandoffPayload, ExtractionResult
from ..tracing.cost_tracker import calculate_call_cost
from ..store.valuation_service import ValuationService
from ..ml.risk_model import ClaimsRiskModel
from .llm_factory import LLMFactory


def _parse_is_late_night(time_str: str, text: str) -> float:
    candidates = [time_str] if time_str else []
    if not candidates and text:
        m = re.search(r'\b(\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?)\b', text, re.IGNORECASE)
        if m:
            candidates.append(m.group(1))
    for cand in candidates:
        s = cand.strip().lower()
        ampm = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)', s)
        if ampm:
            hr = int(ampm.group(1))
            mer = ampm.group(3)
            if mer == "pm" and hr != 12:
                hr += 12
            elif mer == "am" and hr == 12:
                hr = 0
            return 1.0 if (hr >= 23 or hr < 5) else 0.0
        mil = re.search(r'(?:t|\b)(\d{1,2}):(\d{2})', s)
        if mil:
            hr = int(mil.group(1))
            return 1.0 if (hr >= 23 or hr < 5) else 0.0
    return 0.0


def compute_multi_line_policy_math(
    policy_raw: Dict[str, Any],
    extraction: ExtractionResult
) -> Dict[str, Any]:
    """
    100% Deterministic Multi-Line Policy Math (Pure Arithmetic Python).
    Calculates collision limit minus deductible, rental caps (daily & max days),
    and medical payments limits without any LLM float math or hallucination.
    """
    pol_data = policy_raw.get("policy", {})
    raw_status = str(pol_data.get("status", "Active")).strip().lower()
    
    inactive_keywords = ["not active", "inactive", "cancel", "lapse", "expired", "suspended", "void", "terminated"]
    is_inactive = any(kw in raw_status for kw in inactive_keywords)
    is_active = (not is_inactive) and ("active" in raw_status or "current" in raw_status or "in force" in raw_status)

    if is_active:
        resolved_status = "Active"
    elif "cancel" in raw_status:
        resolved_status = "Cancelled"
    elif "suspend" in raw_status:
        resolved_status = "Suspended"
    else:
        resolved_status = "Lapsed"

    cov = policy_raw.get("coverage", {})

    # 1. Collision Coverage Arithmetic
    col_cfg = cov.get("collision", {})
    col_covered = is_active and col_cfg.get("covered", False)
    col_limit = float(col_cfg.get("per_incident_limit") or 0.0) if col_covered else 0.0
    col_deductible = float(col_cfg.get("deductible") or 0.0) if col_covered else 0.0
    # Ceiling is limit minus deductible
    max_col_payout = max(0.0, round(col_limit - col_deductible, 2)) if col_covered and col_limit > 0 else 0.0

    # 2. Rental Reimbursement Arithmetic
    rental_cfg = cov.get("rental_reimbursement", {})
    rental_covered = is_active and rental_cfg.get("covered", False)
    rental_daily_limit = float(rental_cfg.get("daily_limit") or 0.0) if rental_covered else 0.0
    rental_max_days = int(rental_cfg.get("max_days") or 0) if rental_covered else 0
    rental_eligible_payout = 0.0
    rental_notes = None

    if rental_covered and extraction.rental_receipt:
        billed_days = extraction.rental_receipt.days_billed
        billed_rate = extraction.rental_receipt.daily_rate
        eligible_days = min(billed_days, rental_max_days)
        eligible_rate = min(billed_rate, rental_daily_limit)
        rental_eligible_payout = round(eligible_days * eligible_rate, 2)
        rental_notes = (
            f"Rental reimbursement verified: {eligible_days} day(s) @ ${eligible_rate:.2f}/day "
            f"(Billed: {billed_days} days @ ${billed_rate:.2f}/day, policy cap: {rental_max_days} days @ ${rental_daily_limit:.2f}/day)"
        )
    elif extraction.rental_receipt and not rental_covered:
        rental_notes = "Rental receipt submitted but rental reimbursement is not covered on this policy."

    # 3. Medical Payments (MedPay) Arithmetic
    med_cfg = cov.get("medical_payments", {})
    medpay_covered = is_active and med_cfg.get("covered", False)
    medpay_limit = float(med_cfg.get("per_person_limit") or 0.0) if medpay_covered else 0.0
    medpay_eligible_payout = 0.0
    medpay_notes = None

    if medpay_covered and extraction.medical_bills:
        total_billed = sum(b.total_billed for b in extraction.medical_bills)
        medpay_eligible_payout = round(min(total_billed, medpay_limit), 2)
        medpay_notes = (
            f"MedPay verified: ${medpay_eligible_payout:,.2f} eligible "
            f"(Billed: ${total_billed:,.2f}, per-person limit: ${medpay_limit:,.2f})"
        )
    elif extraction.medical_bills and not medpay_covered:
        medpay_notes = "Medical bills submitted but Medical Payments (MedPay) is not covered on this policy."

    # 4. Third-Party Liability Limits
    pd_limit = float(cov.get("property_damage_liability", {}).get("per_incident_limit") or 0.0) if is_active else 0.0
    bi_limit = float(cov.get("bodily_injury_liability", {}).get("per_person_limit") or 0.0) if is_active else 0.0

    return {
        "policy_status": resolved_status,
        "collision_covered": col_covered,
        "collision_limit_per_incident": col_limit if col_covered else None,
        "collision_deductible": col_deductible if col_covered else None,
        "max_eligible_collision_payout": max_col_payout,
        "rental_reimbursement_covered": rental_covered,
        "rental_daily_limit": rental_daily_limit if rental_covered else None,
        "rental_max_days": rental_max_days if rental_covered else None,
        "rental_eligible_payout": rental_eligible_payout,
        "rental_notes": rental_notes,
        "medpay_covered": medpay_covered,
        "medpay_per_person_limit": medpay_limit if medpay_covered else None,
        "medpay_eligible_payout": medpay_eligible_payout,
        "medpay_notes": medpay_notes,
        "property_damage_liability_limit": pd_limit if is_active else None,
        "bodily_injury_per_person_limit": bi_limit if is_active else None,
    }


def investigator_node(state: ClaimState) -> dict:
    """
    Investigator Agent:
    1. DETERMINISTIC STEP 1: Computes pre-accident Actual Cash Value (ACV) and repair-to-ACV ratio via ValuationService.
    2. DETERMINISTIC STEP 2: Evaluates 10 actuarial features through LightGBM risk model for calibrated fraud score & SHAP factor contributions.
    3. DETERMINISTIC STEP 3: Computes multi-line policy limits, deductibles, and eligible payouts via pure arithmetic (min(billed, limit) - deductible).
    4. QUALITATIVE STEP 4: LLM audits policy contract clauses, endorsement riders, exclusions, and third-party liability exposure using generalized reasoning.
    """
    extraction = state.get("extraction")
    if not extraction:
        raise ValueError("Investigator requires extraction to be completed before running.")

    policy_raw = state["policy_raw"]
    policy_str = json.dumps(policy_raw, indent=2)

    # =========================================================================
    # DETERMINISTIC STEP 1: Vehicle Valuation & Total Loss (100% Pure Python)
    # =========================================================================
    val_svc = ValuationService()
    valuation = val_svc.evaluate_claim_repair(
        repair_cost=extraction.claimed_grand_total,
        year=extraction.vehicle_year,
        make=extraction.vehicle_make,
        model=extraction.vehicle_model,
        mileage=extraction.vehicle_mileage or 45000,
        vin=extraction.vehicle_vin
    )

    # =========================================================================
    # DETERMINISTIC STEP 2: LightGBM Tabular Fraud Risk Scoring (100% ML)
    # =========================================================================
    pol_data = policy_raw.get("policy", {})
    claim_hist = policy_raw.get("claim_history", {})
    
    eff_date = pol_data.get("effective_date", "2024-01-01")
    exp_date = pol_data.get("expiration_date", "2027-01-01")
    inc_date = extraction.incident_date or "2026-09-01"
    try:
        d_eff = datetime.strptime(eff_date, "%Y-%m-%d")
        d_inc = datetime.strptime(inc_date, "%Y-%m-%d")
        tenure_months = max(1, int((d_inc - d_eff).days / 30.4))
    except Exception:
        tenure_months = 12

    clm_12 = float(claim_hist.get("claims_in_past_12_months", 0))
    clm_24 = float(claim_hist.get("claims_in_past_24_months", clm_12))
    is_single = 0.0 if extraction.other_party_involved else 1.0
    has_police = 1.0 if extraction.police_report_filed else 0.0
    is_late = _parse_is_late_night(extraction.incident_time or "", extraction.incident_summary)

    ml_features = {
        "policy_age_months": float(tenure_months),
        "claims_frequency_12mo": clm_12,
        "claims_frequency_24mo": clm_24,
        "prior_at_fault_count": clm_12,
        "filing_lag_days": 1.0,
        "policy_inception_gap_days": tenure_months * 30.0,
        "is_single_vehicle": is_single,
        "has_police_report": has_police,
        "is_late_night": is_late,
        "repair_to_acv_ratio": valuation.repair_to_acv_ratio
    }

    risk_engine = ClaimsRiskModel()
    ml_risk = risk_engine.predict_risk(ml_features)

    # =========================================================================
    # DETERMINISTIC STEP 3: Multi-Line Policy Math (Pure Arithmetic Python)
    # =========================================================================
    policy_math = compute_multi_line_policy_math(policy_raw, extraction)

    # Format Policy Endorsements & Legal Clauses
    endorsements = policy_raw.get("active_endorsements", [])
    clauses = policy_raw.get("policy_clauses_and_exclusions", [])

    endorsements_text = "\n".join(
        f"- [{e.get('code', 'RIDER')}] {e.get('title', '')}: {e.get('description', '')}"
        for e in endorsements
    ) if endorsements else "- No optional endorsement riders active on this policy."

    clauses_text = "\n".join(
        f"- [{c.get('clause_id', 'CLAUSE')}] ({c.get('category', 'Condition')}) {c.get('title', '')}: {c.get('text', '')}"
        for c in clauses
    ) if clauses else "- Standard personal auto policy terms."

    # Format full itemized repair operations directly from extraction (no pre-filtering)
    if extraction.itemized_repairs:
        repairs_list = []
        for it in extraction.itemized_repairs:
            part_str = f" (Source: {it.part_type})" if it.part_type else ""
            hours_str = f" [{it.labor_hours} hrs]" if it.labor_hours else ""
            repairs_list.append(f"  • [{it.category.upper()}] {it.description}{part_str}{hours_str}: ${it.amount:,.2f}")
        itemized_repairs_text = "\n".join(repairs_list)
    else:
        itemized_repairs_text = f"  • (No itemized line items extracted; total claimed: ${extraction.claimed_grand_total:,.2f})"

    # Build auxiliary claims summary for prompt
    aux_lines = []
    if extraction.rental_receipt:
        rr = extraction.rental_receipt
        aux_lines.append(f"- Rental Car Invoice: {rr.rental_agency}, {rr.days_billed} days @ ${rr.daily_rate:.2f}/day (Total Billed: ${rr.total_charged:,.2f})")
    if extraction.medical_bills:
        med_total = sum(b.total_billed for b in extraction.medical_bills)
        providers = ", ".join(set(b.provider_name for b in extraction.medical_bills))
        aux_lines.append(f"- Medical Payments Claim: {len(extraction.medical_bills)} bill(s) totaling ${med_total:,.2f} (Provider(s): {providers})")
    if extraction.third_party_claim:
        tp = extraction.third_party_claim
        aux_lines.append(f"- Third-Party Subrogation Demand: Claimant {tp.claimant_name}, Property Damage: ${tp.property_damage_claimed:,.2f}, Bodily Injury: ${tp.bodily_injury_claimed:,.2f} (Summary: {tp.demand_summary})")
    
    auxiliary_claims_summary = "\n".join(aux_lines) if aux_lines else "- No auxiliary rental, medical, or third-party expenses claimed."

    police_info = f"Filed ({extraction.police_report_number or 'Report on file'})" if extraction.police_report_filed else "None filed"
    other_party_info = f"Yes - {extraction.other_party_details or 'Third party involved'}" if extraction.other_party_involved else "No (Single-vehicle incident)"

    shap_factors = (
        "\n".join(f"  • {f['factor']}: {f['detail']} ({f['impact']})" for f in ml_risk.top_risk_factors)
        if ml_risk.top_risk_factors
        else "  • No adverse risk signals detected"
    )

    mileage_display = f"{extraction.vehicle_mileage:,}" if extraction.vehicle_mileage else "Not reported"

    # =========================================================================
    # QUALITATIVE STEP 4: Generalized Contract Clause Auditing & Adjudication (LLM)
    # =========================================================================
    prompt = f"""
You are the Insurance Coverage Investigator Agent.
Your role is to perform qualitative coverage verification, contractual clause auditing, and liability evaluation.

=== 1. POLICY CONTRACT & LEGAL CLAUSES ===
Policy Number: {pol_data.get('policy_number', 'Unknown')}
Policy Status: {policy_math['policy_status']} (Effective: {eff_date} to {exp_date})

Active Endorsement Riders:
{endorsements_text}

Policy Clauses, Exclusions & Conditions:
{clauses_text}

=== 2. CLAIM & LOSS CIRCUMSTANCES (STRUCTURED EXTRACTION) ===
- Claim ID: {extraction.claim_id}
- Incident Date & Time: {extraction.incident_date} {extraction.incident_time or ''}
- Location: {extraction.incident_location}
- Accident Description: {extraction.incident_summary}
- Damaged Vehicle: {extraction.vehicle_year} {extraction.vehicle_make} {extraction.vehicle_model}
- Vehicle Odometer: {mileage_display} miles
- Vehicle VIN: {extraction.vehicle_vin}
- Drivable: {extraction.is_drivable}
- Police Report: {police_info}
- Other Party Involved: {other_party_info}
- Repair Facility: {extraction.repair_facility_name}
- Total Claimed Repair Cost: ${extraction.claimed_grand_total:,.2f} (Parts: ${extraction.total_parts_cost:,.2f}, Labor: ${extraction.total_labor_cost:,.2f}, Add'l: ${extraction.total_additional_costs:,.2f})

=== 2B. ITEMIZED REPAIR ESTIMATE OPERATIONS ===
{itemized_repairs_text}

=== 3. AUXILIARY EXPENSES CLAIMED ===
{auxiliary_claims_summary}

=== 4. PRE-COMPUTED DETERMINISTIC ANALYTICS (DO NOT RECALCULATE) ===
A. Vehicle Valuation & Total Loss (100% Deterministic Python):
   - Pre-Accident Market ACV: ${valuation.actual_cash_value:,.2f}
   - Repair / ACV Ratio: {valuation.repair_to_acv_ratio * 100:.1f}%
   - Total Loss Threshold Triggered (>=75%): {valuation.is_total_loss_candidate}

B. Fraud Risk & Factor Contributions (100% Tabular LightGBM):
   - Calibrated Risk Score: {ml_risk.fraud_risk_score} / 100 ({ml_risk.fraud_risk_level.upper()})
   - SIU Referral Mandatory: {ml_risk.siu_referral_recommended}
   - Top Risk Factors Identified:
{shap_factors}

C. Multi-Line Policy Math (100% Pure Arithmetic Python):
   - Collision: Covered={policy_math['collision_covered']}, Limit=${(policy_math['collision_limit_per_incident'] or 0):,.2f}, Deductible=${(policy_math['collision_deductible'] or 0):,.2f} -> Max Limit Ceiling: ${policy_math['max_eligible_collision_payout']:,.2f}
   - Rental Reimbursement: Covered={policy_math['rental_reimbursement_covered']} -> Eligible Payout: ${policy_math['rental_eligible_payout']:,.2f}
   - Medical Payments: Covered={policy_math['medpay_covered']} -> Eligible Payout: ${policy_math['medpay_eligible_payout']:,.2f}

=== YOUR ADJUDICATION TASKS ===
1. Incident Classification:
   - Classify as 'collision' (impact with vehicle/object), 'comprehensive' (animal, weather, flood, theft), or 'liability_only'.
2. Policy Status & Coverage Verdict:
   - Check if policy was active on incident date. Verdict must be 'covered', 'not_covered' (e.g. lapsed/cancelled/void), or 'partial_coverage'.
3. Case-Specific Policy Contract Clauses & Endorsements Audit:
   - Exclusions ('applied_exclusions'):
     Cross-examine the accident narrative and circumstances against the policy exclusions in Section 1. If any exclusion is triggered (e.g., commercial rideshare/delivery, intentional damage), populate 'applied_exclusions' with the clause ID and explanation.
   - Endorsements ('endorsements_validated'):
     Verify which active endorsement riders apply to the claim (e.g., active OEM parts rider). Populate 'endorsements_validated'.
   - Contract Clause Findings ('clause_audit_notes'):
     Cross-examine the claim facts, vehicle details (e.g. odometer mileage, model year), and all itemized repair operations from Section 2B against every policy clause, condition, endorsement, and sub-limit in Section 1.
     
     GENERAL AUDIT INSTRUCTION FOR EVERY APPLIED CLAUSE:
     Do NOT simply copy, summarize, or quote the general clause definition. For any clause that applies to this claim, provide a DETAILED, EVIDENCE-BASED EXPLANATION:
     1. Specific Evidence: Identify the exact claimed operations, parts (including part sources like OEM/LKQ, custom equipment, wheels), vehicle attributes, or dollar amounts involved.
     2. Why & How it Applies: Explain whether the claimed items comply with or violate the clause, and explicitly state WHY (e.g., why specific parts or charges CAN or CANNOT be reimbursed under the contract, or whether active riders authorize them).
     3. Contractual Effect: Clearly state the practical settlement consequence (e.g. reimbursement restricted to LKQ/aftermarket standard, expense capped at sub-limit, or denied).
     4. Relevance Filter: Only audit clauses relevant to the actual expenses claimed or facts of this loss. Do not include clauses for charges or scenarios that did not occur (e.g., if no storage or towing was billed, do not cite storage caps).
4. Third-Party Liability Assessment:
   - If other party was involved, evaluate driver fault and whether insurer has third-party liability exposure. Populate 'liability_exposure_flag' and 'liability_exposure_summary'.
"""
    structured_llm = LLMFactory.get_structured_llm(InvestigationResult)
    result: InvestigationResult = structured_llm.invoke(prompt)

    # =========================================================================
    # STRICT OVERRIDE: Enforce 100% Deterministic Python & ML Results
    # =========================================================================
    # Set policyholder name from policy contract
    ph = policy_raw.get("policyholder") or policy_raw.get("policy_holder") or pol_data.get("policyholder") or {}
    if isinstance(ph, dict) and ph.get("name"):
        result.policyholder_name = ph.get("name")

    # 1. Deterministic Vehicle Valuation & Total Loss
    result.actual_cash_value = valuation.actual_cash_value
    result.repair_to_acv_ratio = valuation.repair_to_acv_ratio
    result.is_total_loss_candidate = valuation.is_total_loss_candidate

    # 2. Deterministic LightGBM Fraud Risk Scoring
    result.fraud_risk_score = ml_risk.fraud_risk_score
    result.fraud_risk_level = ml_risk.fraud_risk_level
    result.siu_referral_recommended = ml_risk.siu_referral_recommended
    if ml_risk.top_risk_factors:
        result.detected_fraud_signals = [f"{f['factor']}: {f['detail']} ({f['impact']})" for f in ml_risk.top_risk_factors]

    # Actuarial claim history overrides directly from policy database
    result.prior_claims_count_12mo = int(clm_12)
    result.prior_claims_count_24mo = int(clm_24)
    result.policy_tenure_months = tenure_months

    # 3. Deterministic Multi-Line Policy Math
    result.collision_covered = policy_math["collision_covered"]
    result.collision_limit_per_incident = policy_math["collision_limit_per_incident"]
    result.collision_deductible = policy_math["collision_deductible"]
    result.max_eligible_collision_payout = policy_math["max_eligible_collision_payout"]

    result.rental_reimbursement_covered = policy_math["rental_reimbursement_covered"]
    result.rental_daily_limit = policy_math["rental_daily_limit"]
    result.rental_max_days = policy_math["rental_max_days"]
    result.rental_eligible_payout = policy_math["rental_eligible_payout"]
    if policy_math["rental_notes"]:
        result.rental_notes = policy_math["rental_notes"]

    result.medpay_covered = policy_math["medpay_covered"]
    result.medpay_per_person_limit = policy_math["medpay_per_person_limit"]
    result.medpay_eligible_payout = policy_math["medpay_eligible_payout"]
    if policy_math["medpay_notes"]:
        result.medpay_notes = policy_math["medpay_notes"]

    result.property_damage_liability_limit = policy_math["property_damage_liability_limit"]
    result.bodily_injury_per_person_limit = policy_math["bodily_injury_per_person_limit"]

    # Enforce deterministic policy status from document
    result.policy_status = policy_math["policy_status"]

    # Void/Lapsed policy guard: zero out all payouts if not covered or policy inactive
    if result.coverage_verdict == "not_covered" or policy_math["policy_status"] in ("Lapsed", "Cancelled", "Suspended"):
        result.coverage_verdict = "not_covered"
        result.coverage_denial_reason = f"Policy is {policy_math['policy_status'].lower()} at date of loss."
        result.collision_covered = False
        result.rental_reimbursement_covered = False
        result.medpay_covered = False
        result.max_eligible_collision_payout = 0.0
        result.rental_eligible_payout = 0.0
        result.medpay_eligible_payout = 0.0

    tokens_used, cost_usd = calculate_call_cost({
        "input_tokens": 1500,
        "output_tokens": 480,
        "total_tokens": 1980
    })

    coverage_details = [f"Collision: ${result.max_eligible_collision_payout or 0:,.2f}"]
    if result.rental_eligible_payout > 0:
        coverage_details.append(f"Rental: ${result.rental_eligible_payout:,.2f}")
    if result.medpay_eligible_payout > 0:
        coverage_details.append(f"MedPay: ${result.medpay_eligible_payout:,.2f}")
    if result.is_total_loss_candidate:
        coverage_details.append(f"TOTAL LOSS ({result.repair_to_acv_ratio * 100:.1f}% ACV)")
    
    clause_notes_count = len(result.clause_audit_notes) if result.clause_audit_notes else 0
    clause_summary = f" [Clauses: {clause_notes_count} audited]" if clause_notes_count else ""

    handoff = HandoffPayload(
        source_node="investigator",
        target_node="supervisor",
        action="INVESTIGATE",
        claim_id=state["claim_id"],
        step_number=state["step_count"] + 1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        summary=f"Coverage verdict: {result.coverage_verdict.upper()} ({', '.join(coverage_details)}) [LightGBM Risk: {result.fraud_risk_level.upper()} {result.fraud_risk_score}/100]{clause_summary}"
    )

    return {
        "investigation": result,
        "step_count": state["step_count"] + 1,
        "total_tokens": state["total_tokens"] + tokens_used,
        "total_cost_usd": state["total_cost_usd"] + cost_usd,
        "handoff_history": state["handoff_history"] + [handoff],
        "current_phase": "investigation"
    }
