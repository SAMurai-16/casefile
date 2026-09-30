#!/usr/bin/env python3
"""
Standalone CLI tool to run and inspect the Investigator Node in CaseFile.

Tests the Investigator Agent in isolation across its core responsibilities:
  1. Deterministic Vehicle Valuation & Total Loss (ValuationService)
  2. Tabular LightGBM Fraud Risk Scoring & SHAP Factors (ClaimsRiskModel)
  3. Deterministic Multi-Line Policy Math (Collision, Rental, MedPay limits)
  4. Qualitative Contract Clause & Endorsement Auditing (LLM)

Usage examples:
    # 1. Run investigator on a built-in claim:
    python scripts/test_investigator.py 001
    python scripts/test_investigator.py 002

    # 2. Run all benchmark claims (001-005) with comparison summary:
    python scripts/test_investigator.py --all

    # 3. Output full JSON payload directly to stdout (useful for piping to jq):
    python scripts/test_investigator.py 001 --json

    # 4. Test with specific LLM provider (mock, gemini, openai):
    python scripts/test_investigator.py 001 --provider mock
    python scripts/test_investigator.py 001 --provider gemini

    # 5. Save output JSON directly to a file:
    python scripts/test_investigator.py 001 --output investigation_001.json
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from casefile.config import DATA_DIR, DEFAULT_PROVIDER
from casefile.store.claim_store import ClaimStore
from casefile.schema import ClaimState, ExtractionResult, InvestigationResult
from casefile.agents.extractor import extractor_node
from casefile.agents.investigator import investigator_node


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run CaseFile Investigator node in isolation and inspect all 4 evaluation pillars.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_investigator.py 001
  python scripts/test_investigator.py 002 --json
  python scripts/test_investigator.py --all
  python scripts/test_investigator.py 001 --provider gemini
"""
    )
    parser.add_argument(
        "claim_id",
        nargs="?",
        default=None,
        help="Claim number or ID to load from data directory (e.g., 001, 002, CLM-2026-00147)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run investigator across all 5 benchmark claims (001-005) and display summary comparison."
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "gemini", "openai"],
        default=None,
        help=f"Override LLM provider for this execution (default: {DEFAULT_PROVIDER} or .env)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw InvestigationResult JSON to stdout."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Save the InvestigationResult JSON output to a designated file path."
    )
    return parser.parse_args()


def print_formatted_investigation(result: InvestigationResult, meta: Dict[str, Any]):
    """Pretty-prints the InvestigationResult object in a human-readable executive format."""
    print("=" * 80)
    print(f"CASEFILE: INVESTIGATOR AGENT STANDALONE EVALUATION")
    print(f"Claim ID:       {result.claim_id}")
    print(f"Policy Number:  {result.policy_number} (Status: {result.policy_status})")
    print(f"Coverage Term:  {result.policy_effective_date} to {result.policy_expiration_date}")
    print(f"Classification: {result.incident_classification.upper()}")
    print(f"Overall Verdict:{result.coverage_verdict.upper()} {f'— Denial: {result.coverage_denial_reason}' if result.coverage_denial_reason else ''}")
    print("=" * 80)

    # 1. Vehicle Valuation & Total Loss (100% Deterministic Python)
    print("\n[PILLAR 1: DETERMINISTIC VEHICLE VALUATION & TOTAL LOSS]")
    acv = result.actual_cash_value or 0.0
    ratio = (result.repair_to_acv_ratio or 0.0) * 100
    print(f"  • Pre-Accident Market ACV:  ${acv:,.2f}")
    print(f"  • Repair-to-ACV Ratio:      {ratio:.1f}%")
    if result.is_total_loss_candidate:
        print(f"  • Total Loss Status:        🚨 TRIGGERED (Repair >= 75% of vehicle value)")
    else:
        print(f"  • Total Loss Status:        No (Economically repairable)")

    # 2. Fraud Risk & Factor Contributions (100% Deterministic ML)
    print("\n[PILLAR 2: DETERMINISTIC LIGHTGBM FRAUD RISK SCORING]")
    tier_emojis = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    emoji = tier_emojis.get(result.fraud_risk_level, "⚪")
    print(f"  • Calibrated Risk Score:    {emoji} {result.fraud_risk_score} / 100 ({result.fraud_risk_level.upper()})")
    print(f"  • SIU Referral Mandatory:   {'YES (Escalate to Special Investigation Unit)' if result.siu_referral_recommended else 'No'}")
    print(f"  • Actuarial Claim History:  {result.prior_claims_count_12mo} claim(s) in 12mo | {result.prior_claims_count_24mo} claim(s) in 24mo (Tenure: {result.policy_tenure_months or 0} mos)")
    if result.detected_fraud_signals:
        print("  • Identified Risk Signals (SHAP Factors):")
        for sig in result.detected_fraud_signals:
            print(f"      - {sig}")
    else:
        print("  • Identified Risk Signals:  None (Clean risk profile)")

    # 3. Multi-Line Policy Math (100% Pure Arithmetic Python)
    print("\n[PILLAR 3: DETERMINISTIC MULTI-LINE POLICY MATH]")
    col_status = "Covered" if result.collision_covered else "Not Covered / Void"
    print(f"  • Collision Coverage:       {col_status}")
    if result.collision_covered:
        print(f"      - Incident Limit:       ${(result.collision_limit_per_incident or 0):,.2f}")
        print(f"      - Deductible:           ${(result.collision_deductible or 0):,.2f}")
        print(f"      - Max Eligible Ceiling: ${(result.max_eligible_collision_payout or 0):,.2f} (Limit minus Deductible)")
    else:
        print(f"      - Max Eligible Payout:  $0.00")

    rental_status = "Covered" if result.rental_reimbursement_covered else "Not Covered"
    print(f"  • Rental Reimbursement:     {rental_status}")
    if result.rental_reimbursement_covered:
        print(f"      - Daily Limit / Max:    ${(result.rental_daily_limit or 0):.2f}/day (Up to {result.rental_max_days or 0} days)")
        print(f"      - Eligible Payout:      ${result.rental_eligible_payout:,.2f}")
        if result.rental_notes:
            print(f"      - Audit Calculation:    {result.rental_notes}")

    med_status = "Covered" if result.medpay_covered else "Not Covered"
    print(f"  • Medical Payments (MedPay):{med_status}")
    if result.medpay_covered:
        print(f"      - Per-Person Limit:     ${(result.medpay_per_person_limit or 0):,.2f}")
        print(f"      - Eligible Payout:      ${result.medpay_eligible_payout:,.2f}")
        if result.medpay_notes:
            print(f"      - Audit Calculation:    {result.medpay_notes}")

    print(f"  • Third-Party Liability:    Exposure Flag = {result.liability_exposure_flag}")
    if result.property_damage_liability_limit:
        print(f"      - Limits In Force:      PD: ${(result.property_damage_liability_limit or 0):,.2f} | BI: ${(result.bodily_injury_per_person_limit or 0):,.2f}")
    if result.liability_exposure_summary:
        print(f"      - Exposure Summary:     {result.liability_exposure_summary}")

    # 4. Policy Contract Clauses & Endorsement Auditing (Qualitative LLM)
    print("\n[PILLAR 4: POLICY CONTRACT & CLAUSE AUDITING]")
    if result.endorsements_validated:
        for end in result.endorsements_validated:
            print(f"  📜 Active Endorsement:      {end}")
    else:
        print(f"  📜 Active Endorsements:      None")

    if result.applied_exclusions:
        for excl in result.applied_exclusions:
            print(f"  🚫 Exclusion Triggered:     {excl}")
    else:
        print(f"  🚫 Exclusions Triggered:    None (No exclusions violated)")

    if result.clause_audit_notes:
        for note in result.clause_audit_notes:
            print(f"  ⚖️  Contract Clause Audit:   {note}")
    else:
        print(f"  ⚖️  Contract Clause Audit:   Standard policy conditions satisfied")

    # 5. Telemetry & Handoff Summary
    print("\n" + "-" * 80)
    print("EXECUTION TELEMETRY & SUPERVISOR HANDOFF")
    print(f"  • Tokens Consumed:          {meta.get('tokens', 0):,}")
    print(f"  • Estimated Cost:           ${meta.get('cost_usd', 0.0):.4f}")
    print(f"  • Execution Time:           {meta.get('elapsed_sec', 0.0):.2f}s")
    handoff = meta.get("handoff")
    if handoff:
        print(f"  • Handoff Action:           {handoff.action}")
        print(f"  • Handoff Summary:          {handoff.summary}")
    print("=" * 80 + "\n")


def run_investigator_on_claim(claim_id_input: str, provider: Optional[str] = None) -> tuple[InvestigationResult, Dict[str, Any]]:
    """Runs the Extractor and Investigator nodes in sequence for a single claim."""
    if provider:
        os.environ["LLM_PROVIDER"] = provider

    store = ClaimStore()
    claim_num = claim_id_input.replace("claim_", "").replace("CLM-2026-", "").replace("CLM-", "").lstrip("0") or "1"
    formatted_num = f"{int(claim_num):03d}"
    claim_id_label = f"CLM-2026-{10000 + int(claim_num)}"

    fnol, est, pol, rental, med, tp = store.load_claim_package(formatted_num)

    state: ClaimState = {
        "claim_id": claim_id_label,
        "run_id": f"test_inv_{int(claim_num)}",
        "thread_id": f"thread_{claim_id_label}",
        "fnol_raw": fnol,
        "estimate_raw": est,
        "policy_raw": pol,
        "rental_raw": rental,
        "medical_raw": med,
        "third_party_raw": tp,
        "extraction": None,
        "investigation": None,
        "review": None,
        "human_decision": None,
        "current_phase": "intake",
        "step_count": 0,
        "rework_count": 0,
        "handoff_history": [],
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "budget_exceeded": False,
        "max_steps_exceeded": False,
        "terminal_status": None,
        "payout_breakdown": None,
        "final_payout_amount": None,
        "settlement_summary": None,
    }

    # Step 1: Run extractor to produce structured extraction
    ext_state = extractor_node(state)
    state["extraction"] = ext_state["extraction"]
    state["step_count"] = ext_state["step_count"]
    state["total_tokens"] = ext_state["total_tokens"]
    state["total_cost_usd"] = ext_state["total_cost_usd"]
    state["handoff_history"] = ext_state["handoff_history"]

    # Step 2: Run investigator in isolation
    t0 = time.time()
    inv_state = investigator_node(state)
    elapsed = time.time() - t0

    result: InvestigationResult = inv_state["investigation"]
    meta = {
        "tokens": inv_state.get("total_tokens", 0) - ext_state.get("total_tokens", 0),
        "cost_usd": inv_state.get("total_cost_usd", 0.0) - ext_state.get("total_cost_usd", 0.0),
        "elapsed_sec": elapsed,
        "handoff": inv_state.get("handoff_history", [None])[-1] if inv_state.get("handoff_history") else None
    }
    return result, meta


def run_all_benchmark_claims(provider: Optional[str] = None):
    """Executes Investigator across all 5 standard benchmark claims and prints a comparative table."""
    print("\n" + "=" * 95)
    print("CASEFILE: INVESTIGATOR AGENT BENCHMARK SUITE (CLAIMS 001 - 005)")
    print("=" * 95)

    benchmarks = ["001", "002", "003", "004", "005"]
    summaries = []

    for b in benchmarks:
        result, meta = run_investigator_on_claim(b, provider=provider)
        acv = result.actual_cash_value or 0.0
        ratio = (result.repair_to_acv_ratio or 0.0) * 100
        summaries.append({
            "claim": f"CLM-{b}",
            "status": result.policy_status,
            "verdict": result.coverage_verdict,
            "acv": f"${acv:,.0f}",
            "ratio": f"{ratio:.1f}%",
            "total_loss": "YES" if result.is_total_loss_candidate else "No",
            "fraud_score": f"{result.fraud_risk_score}/100 ({result.fraud_risk_level[:4].upper()})",
            "siu": "SIU" if result.siu_referral_recommended else "Normal",
            "max_col": f"${(result.max_eligible_collision_payout or 0):,.2f}",
            "rental": f"${result.rental_eligible_payout:,.2f}",
            "medpay": f"${result.medpay_eligible_payout:,.2f}",
            "clauses": len(result.clause_audit_notes) + len(result.applied_exclusions) + len(result.endorsements_validated),
        })

    # Print Table
    header = f"{'Claim':<9} | {'Policy':<9} | {'Verdict':<10} | {'ACV':<8} | {'Rep/ACV':<8} | {'TotLoss':<7} | {'Risk Score':<15} | {'SIU':<6} | {'Max Col':<11} | {'Rental':<8} | {'MedPay':<8} | {'Clauses'}"
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(f"{s['claim']:<9} | {s['status']:<9} | {s['verdict']:<10} | {s['acv']:<8} | {s['ratio']:<8} | {s['total_loss']:<7} | {s['fraud_score']:<15} | {s['siu']:<6} | {s['max_col']:<11} | {s['rental']:<8} | {s['medpay']:<8} | {s['clauses']} audited")
    print("=" * 95 + "\n")


def main():
    args = parse_args()
    provider_name = args.provider or os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)

    if args.all:
        run_all_benchmark_claims(provider=provider_name)
        return

    claim_target = args.claim_id or "001"
    result, meta = run_investigator_on_claim(claim_target, provider=provider_name)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2, default=str))
    else:
        print_formatted_investigation(result, meta)

    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(result.model_dump(), indent=2, default=str))
        if not args.json:
            print(f"Investigation output saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
