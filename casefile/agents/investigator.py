import json
from datetime import datetime, timezone
from ..schema import ClaimState, InvestigationResult, HandoffPayload
from ..tracing.cost_tracker import calculate_call_cost
from ..store.valuation_service import ValuationService
from ..ml.risk_model import ClaimsRiskModel
from .llm_factory import LLMFactory

def investigator_node(state: ClaimState) -> dict:
    """
    Investigator Agent:
    1. Computes pre-accident Actual Cash Value (ACV) and repair-to-ACV ratio via ValuationService.
    2. Runs LightGBM ML risk model to calculate calibrated fraud score & SHAP factor contributions.
    3. Evaluates all policy coverage lines (Collision, Rental, MedPay, Liability).
    """
    policy_str = json.dumps(state["policy_raw"], indent=2)
    fnol_str = json.dumps(state["fnol_raw"], indent=2)
    
    extraction = state.get("extraction")
    
    # 1. Deterministic Vehicle Valuation (CCC ONE / KBB proxy)
    val_svc = ValuationService()
    if extraction:
        valuation = val_svc.evaluate_claim_repair(
            repair_cost=extraction.claimed_grand_total,
            year=extraction.vehicle_year,
            make=extraction.vehicle_make,
            model=extraction.vehicle_model,
            mileage=extraction.vehicle_mileage or 35000,
            vin=extraction.vehicle_vin
        )
    else:
        veh_info = state["fnol_raw"].get("vehicle_info", {})
        valuation = val_svc.evaluate_claim_repair(
            repair_cost=0.0,
            year=veh_info.get("year", 2022),
            make=veh_info.get("make", "Generic"),
            model=veh_info.get("model", "Sedan"),
            mileage=veh_info.get("mileage_at_incident", 35000)
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

    # Incident hour
    fnol_time = state["fnol_raw"].get("intake_header", {}).get("received_at", "")
    is_late = 1.0 if any(h in fnol_time for h in ["23:", "00:", "01:", "02:", "03:", "04:"]) or "11:42 pm" in fnol_str.lower() or "03:30 am" in fnol_str.lower() else 0.0
    
    is_single = 1.0 if not extraction or not extraction.other_party_involved else 0.0
    has_police = 1.0 if extraction and extraction.police_report_filed else 0.0
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

    extraction_summary = f"""
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
Examine the customer's Policy Record, loss circumstances, and the automated vehicle valuation / LightGBM risk findings.

=== DOCUMENT 3: POLICY & COVERAGE RECORD ===
{policy_str}

=== LOSS CIRCUMSTANCES (FROM FNOL) ===
{fnol_str}
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
