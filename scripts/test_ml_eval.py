import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from casefile.store.valuation_service import ValuationService
from casefile.ml.risk_model import ClaimsRiskModel

def run_ml_check():
    val_svc = ValuationService()
    risk_model = ClaimsRiskModel()

    print("=" * 70)
    print("LIGHTGBM + ACV RISK SCORING EVALUATION")
    print("=" * 70)

    test_claims = [
        ("Claim 001 (Honda Civic)", 4017.79, 2023, "Honda", "Civic", 28450, 30, 0, 1, 0, 1, 0),
        ("Claim 002 (BMW 330i)", 12590.70, 2022, "BMW", "330i", 41200, 3, 2, 3, 1, 0, 1),
        ("Claim 003 (Toyota RAV4)", 1004.86, 2024, "Toyota", "RAV4", 11800, 20, 0, 0, 0, 0, 0),
        ("Claim 004 (Mercedes C300)", 23974.97, 2020, "Mercedes-Benz", "C300", 68700, 2, 3, 5, 1, 0, 1),
        ("Claim 005 (Nissan Altima)", 7878.00, 2021, "Nissan", "Altima", 52100, 0, 1, 2, 0, 1, 0),
    ]

    for label, repair, yr, make, model, mi, age_mo, clm12, clm24, single, police, late in test_claims:
        v = val_svc.evaluate_claim_repair(repair, yr, make, model, mi)
        features = {
            "policy_age_months": float(age_mo),
            "claims_frequency_12mo": float(clm12),
            "claims_frequency_24mo": float(clm24),
            "prior_at_fault_count": float(clm12),
            "filing_lag_days": 1.0,
            "policy_inception_gap_days": float(age_mo * 30),
            "is_single_vehicle": float(single),
            "has_police_report": float(police),
            "is_late_night": float(late),
            "repair_to_acv_ratio": v.repair_to_acv_ratio
        }
        assessment = risk_model.predict_risk(features)
        
        print(f"\n{label}:")
        print(f"  • Pre-Accident Market ACV: ${v.actual_cash_value:,.2f}")
        print(f"  • Repair Cost:             ${repair:,.2f}")
        print(f"  • Repair / ACV Ratio:      {v.repair_to_acv_ratio * 100:.1f}% {'(TOTAL LOSS CANDIDATE)' if v.is_total_loss_candidate else ''}")
        print(f"  • LightGBM Fraud Score:    {assessment.fraud_risk_score} / 100 [{assessment.fraud_risk_level.upper()}]")
        print(f"  • SIU Referral Mandatory:  {assessment.siu_referral_recommended}")
        if assessment.top_risk_factors:
            print("  • Key Risk Factors (SHAP Contributions):")
            for f in assessment.top_risk_factors:
                print(f"      - {f['factor']}: {f['detail']} ({f['impact']})")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    run_ml_check()
