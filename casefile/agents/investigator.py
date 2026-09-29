import json
import re
from datetime import datetime, timezone
from ..schema import ClaimState, InvestigationResult, HandoffPayload
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


def investigator_node(state: ClaimState) -> dict:
    """
    Investigator Agent:
    1. Reads structured Extraction findings and raw Policy contract.
    2. Computes pre-accident Actual Cash Value (ACV) and repair-to-ACV ratio via ValuationService.
    3. Runs LightGBM ML risk model to calculate calibrated fraud score & SHAP factor contributions.
    4. Evaluates all policy coverage lines (Collision, Rental, MedPay, Liability).
    """
    extraction = state.get("extraction")
    if not extraction:
        raise ValueError("Investigator requires extraction to be completed before running.")

    policy_str = json.dumps(state["policy_raw"], indent=2)

    # 1. Deterministic Vehicle Valuation (CCC ONE / KBB proxy)
    val_svc = ValuationService()
    valuation = val_svc.evaluate_claim_repair(
        repair_cost=extraction.claimed_grand_total,
        year=extraction.vehicle_year,
        make=extraction.vehicle_make,
        model=extraction.vehicle_model,
        mileage=extraction.vehicle_mileage or 35000,
        vin=extraction.vehicle_vin
    )

    # 2. Extract Features for LightGBM Risk Model
    pol_data = state["policy_raw"].get("policy", {})
    claim_hist = state["policy_raw"].get("claim_history", {})
    
    # Calculate policy tenure
    eff_date = pol_data.get("effective_date", "2024-01-01")
    try:
        eff_dt = datetime.strptime(eff_date, "%Y-%m-%d")
        now_dt = datetime.now()
        tenure_months = max(1.0, (now_dt.year - eff_dt.year) * 12 + (now_dt.month - eff_dt.month))
    except Exception:
        tenure_months = 24.0

    # Incident hour (Late-night window: 11:00 PM - 4:59 AM)
    incident_time_raw = extraction.incident_time or ""
    is_late = _parse_is_late_night(incident_time_raw, extraction.incident_summary)
    
    is_single = 1.0 if not extraction.other_party_involved else 0.0
    has_police = 1.0 if extraction.police_report_filed else 0.0
    clm_24 = float(claim_hist.get("claims_last_24_months", 0))
    clm_12 = float(claim_hist.get("claims_last_12_months", 0))

    ml_features = {
        "policy_age_months": tenure_months,
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

    # 3. Predict Fraud Risk via LightGBM
    risk_engine = ClaimsRiskModel()
    ml_risk = risk_engine.predict_risk(ml_features)

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

    extraction_summary = f"""
=== CLAIM & LOSS CIRCUMSTANCES (STRUCTURED EXTRACTION) ===
- Claim ID: {extraction.claim_id}
- Incident Date & Time: {extraction.incident_date} {extraction.incident_time or ''}
- Location: {extraction.incident_location}
- Accident Description: {extraction.incident_summary}
- Damaged Vehicle: {extraction.vehicle_year} {extraction.vehicle_make} {extraction.vehicle_model} (VIN: {extraction.vehicle_vin})
- Drivable: {extraction.is_drivable}
- Police Report: {police_info}
- Other Party Involved: {other_party_info}
- Claimed Body Shop Repair Cost: ${extraction.claimed_grand_total:,.2f} (Facility: {extraction.repair_facility_name})
=== AUXILIARY EXPENSES CLAIMED ===
{auxiliary_claims_summary}

=== VEHICLE VALUATION & TOTAL LOSS AUDIT ===
- Pre-Accident Market ACV: ${valuation.actual_cash_value:,.2f}
- Claimed Repair Cost: ${valuation.repair_estimate_total:,.2f}
- Repair / ACV Ratio: {valuation.repair_to_acv_ratio * 100:.1f}%
- Total Loss Threshold Triggered: {valuation.is_total_loss_candidate}

=== LIGHTGBM ML FRAUD RISK MODEL RESULTS ===
- Calibrated Risk Score: {ml_risk.fraud_risk_score} / 100 ({ml_risk.fraud_risk_level.upper()})
- SIU Referral Mandatory: {ml_risk.siu_referral_recommended}
- Top Risk Factors Identified:
{chr(10).join(f"  • {f['factor']}: {f['detail']} ({f['impact']})" for f in ml_risk.top_risk_factors) if ml_risk.top_risk_factors else "  • No adverse risk signals detected"}
"""

    prompt = f"""
You are the Insurance Coverage Investigator Agent.
Examine the customer's Policy Record, structured loss circumstances, and the automated vehicle valuation / LightGBM risk findings.

=== DOCUMENT: POLICY & COVERAGE RECORD ===
{policy_str}
{extraction_summary}

Adjudication Tasks:
1. Verify policy status (Active vs Lapsed/Cancelled).
2. Collision Coverage: Determine collision limit and deductible, and calculate max eligible repair payout.
3. Incorporate Vehicle Valuation:
   - actual_cash_value: {valuation.actual_cash_value}
   - repair_to_acv_ratio: {valuation.repair_to_acv_ratio}
   - is_total_loss_candidate: {valuation.is_total_loss_candidate}
4. Rental Reimbursement: If covered and rental claimed, calculate eligible rental payout.
5. Medical Payments: If covered and medical bills present, calculate eligible MedPay payout.
6. Third-Party Liability: Assess exposure if insured was at fault with third-party claims.
7. Fraud Risk: Use the LightGBM score of {ml_risk.fraud_risk_score} and tier '{ml_risk.fraud_risk_level}'.
"""
    structured_llm = LLMFactory.get_structured_llm(InvestigationResult)
    result: InvestigationResult = structured_llm.invoke(prompt)

    # Ensure deterministic ML values are always explicitly preserved on the result object
    result.actual_cash_value = valuation.actual_cash_value
    result.repair_to_acv_ratio = valuation.repair_to_acv_ratio
    result.is_total_loss_candidate = valuation.is_total_loss_candidate
    result.fraud_risk_score = ml_risk.fraud_risk_score
    result.fraud_risk_level = ml_risk.fraud_risk_level
    result.siu_referral_recommended = ml_risk.siu_referral_recommended
    if ml_risk.top_risk_factors:
        result.detected_fraud_signals = [f"{f['factor']}: {f['detail']} ({f['impact']})" for f in ml_risk.top_risk_factors]

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
    
    handoff = HandoffPayload(
        source_node="investigator",
        target_node="supervisor",
        action="INVESTIGATE",
        claim_id=state["claim_id"],
        step_number=state["step_count"] + 1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        summary=f"Coverage verdict: {result.coverage_verdict.upper()} ({', '.join(coverage_details)}) [LightGBM Risk: {result.fraud_risk_level.upper()} {result.fraud_risk_score}/100]"
    )

    return {
        "investigation": result,
        "step_count": state["step_count"] + 1,
        "total_tokens": state["total_tokens"] + tokens_used,
        "total_cost_usd": state["total_cost_usd"] + cost_usd,
        "handoff_history": state["handoff_history"] + [handoff],
        "current_phase": "investigation"
    }
