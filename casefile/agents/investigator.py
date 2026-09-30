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
    raw_status = pol_data.get("status", "Active")
    is_active = "active" in raw_status.lower()

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
        "policy_status": "Active" if is_active else ("Cancelled" if "cancel" in raw_status.lower() else "Lapsed"),
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
    4. QUALITATIVE STEP 4: LLM audits policy contract clauses, endorsement riders, exclusions, and third-party liability exposure with case-specific facts.
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

    # Build repair parts and charges breakdown for evidence-based contract audit
    parts_items = [it for it in (extraction.itemized_repairs or []) if it.category == "parts"]
    oem_parts = [it for it in parts_items if (it.part_type or "").upper() == "OEM"]
    non_oem_parts = [it for it in parts_items if (it.part_type or "").upper() != "OEM"]
    towing_items = [it for it in (extraction.itemized_repairs or []) if it.category == "towing_storage"]

    parts_summary_lines = []
    if parts_items:
        parts_summary_lines.append(f"- Total Parts Billed: {len(parts_items)} items totaling ${sum(p.amount for p in parts_items):,.2f}")
        if oem_parts:
            oem_total = sum(p.amount for p in oem_parts)
            oem_sample = ", ".join(p.description for p in oem_parts[:4])
            parts_summary_lines.append(f"  • OEM Parts Billed: {len(oem_parts)} items totaling ${oem_total:,.2f} (Includes: {oem_sample})")
        if non_oem_parts:
            non_oem_total = sum(p.amount for p in non_oem_parts)
            non_oem_sample = ", ".join(p.description for p in non_oem_parts[:4])
            parts_summary_lines.append(f"  • Non-OEM/LKQ/Aftermarket Parts Billed: {len(non_oem_parts)} items totaling ${non_oem_total:,.2f} (Includes: {non_oem_sample})")
    else:
        parts_summary_lines.append(f"- Total Parts Billed: ${extraction.total_parts_cost:,.2f} (Itemized breakdown not available)")

    # Flag custom equipment or wheel items
    custom_items = [
        it for it in (extraction.itemized_repairs or [])
        if any(k in it.description.lower() for k in ["wheel", "rim", "alloy", "custom", "audio", "wrap", "spoiler", "m-sport"])
    ]
    if custom_items:
        for ci in custom_items:
            parts_summary_lines.append(f"  • Custom/Aftermarket Item Flagged: '{ci.description}' billed at ${ci.amount:,.2f} ({ci.part_type or 'Part'})")

    if towing_items:
        towing_total = sum(t.amount for t in towing_items)
        parts_summary_lines.append(f"- Towing/Impound Storage Charges: {len(towing_items)} item(s) totaling ${towing_total:,.2f}")
    else:
        parts_summary_lines.append("- Towing/Impound Storage Charges: None billed on repair invoice ($0.00)")

    repair_parts_summary = "\n".join(parts_summary_lines)

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
    # QUALITATIVE STEP 4: Contract Clause Auditing & Coverage Adjudication (LLM)
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

=== 2B. BILLED REPAIR PARTS & CHARGES AUDIT ===
{repair_parts_summary}

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
3. Case-Specific Policy Contract Clauses & Endorsement Auditing:
   - Exclusions: Check if loss facts trigger exclusions (e.g. Commercial Rideshare Exclusion SEC-IV-EXCL-3). Populate 'applied_exclusions'.
   - Endorsements: Verify active riders (e.g. END-OEM-01). Populate 'endorsements_validated'.
   - Specific Clause Audit Notes ('clause_audit_notes'):
     IMPORTANT: DO NOT simply quote or restate abstract policy text. Each note MUST explain HOW and WHY the clause applies to THIS claim's specific facts and figures:
     a) LKQ Parts Rule (SEC-IV-COND-7):
        - Cross-examine the vehicle's odometer ({mileage_display} miles) and model year ({extraction.vehicle_year}) against the 25,000-mile / 2-year threshold.
        - Check Section 2B: Did the shop bill OEM parts?
        - If OEM parts were billed AND Endorsement END-OEM-01 is NOT active: explicitly state that OEM parts CANNOT be reimbursed under the policy, explain WHY they are denied (vehicle has over 25,000 miles and the insured declined the OEM rider), and note that reimbursement is legally restricted to Like-Kind-and-Quality (LKQ) / certified aftermarket pricing.
        - If END-OEM-01 IS active: explain that 100% OEM parts are authorized under the active rider despite the vehicle's mileage.
     b) Custom Equipment Sub-Limit (SEC-IV-LIMIT-4):
        - Check Section 2B for custom equipment or alloy wheels (e.g. M-Sport alloy wheel).
        - State the specific item name and exact billed dollar amount, and verify if it is within or exceeds the $1,000.00 sub-limit.
     c) Storage & Impound Cap (SEC-IV-LIMIT-5):
        - Check Section 2B: If no impound/storage fees were billed on this estimate, DO NOT list this clause. Only audit clauses where expenses were actually claimed.
4. Third-Party Liability Assessment:
   - If other party was involved, evaluate driver fault and whether insurer has third-party liability exposure. Populate 'liability_exposure_flag' and 'liability_exposure_summary'.
"""
    structured_llm = LLMFactory.get_structured_llm(InvestigationResult)
    result: InvestigationResult = structured_llm.invoke(prompt)

    # =========================================================================
    # STRICT OVERRIDE: Enforce 100% Deterministic Python & ML Results
    # =========================================================================
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

    # Void/Lapsed policy guard: zero out all payouts if not covered or policy inactive
    if result.coverage_verdict == "not_covered" or policy_math["policy_status"] in ("Lapsed", "Cancelled", "Suspended"):
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
