#!/usr/bin/env python3
"""
Standalone CLI tool to run and inspect the Extractor Node in CaseFile.

Usage examples:
    # 1. Run extractor on a built-in claim:
    python scripts/test_extractor.py 001
    python scripts/test_extractor.py CLM-2026-00203

    # 2. Output full JSON payload directly to stdout (useful for piping to jq):
    python scripts/test_extractor.py 001 --json

    # 3. Test on custom document files:
    python scripts/test_extractor.py --fnol path/to/fnol.json --estimate path/to/estimate.json

    # 4. Include optional auxiliary files:
    python scripts/test_extractor.py --fnol fnol.json --estimate est.json --rental rental.json --medical med.json

    # 5. Test with specific LLM provider (gemini, openai, mock):
    python scripts/test_extractor.py 001 --provider mock
    python scripts/test_extractor.py 001 --provider gemini

    # 6. Save output JSON directly to a file:
    python scripts/test_extractor.py 001 --output extracted_001.json
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from casefile.config import DATA_DIR, DEFAULT_PROVIDER
from casefile.store.claim_store import ClaimStore
from casefile.schema import ClaimState, ExtractionResult
from casefile.agents.extractor import extractor_node


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run CaseFile Extractor node in isolation and inspect the extracted schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_extractor.py 001
  python scripts/test_extractor.py 002 --json
  python scripts/test_extractor.py --fnol fnol.json --estimate est.json
  python scripts/test_extractor.py 001 --provider gemini
"""
    )
    # Positional or optional claim ID
    parser.add_argument(
        "claim_id",
        nargs="?",
        default=None,
        help="Claim number or ID to load from data directory (e.g., 001, 002, CLM-2026-00147)"
    )
    
    # Custom document paths
    parser.add_argument("--fnol", type=str, default=None, help="Path to raw FNOL JSON file")
    parser.add_argument("--estimate", type=str, default=None, help="Path to raw Repair Estimate JSON file")
    parser.add_argument("--rental", type=str, default=None, help="Optional path to Rental Receipt JSON file")
    parser.add_argument("--medical", type=str, default=None, help="Optional path to Medical Bill JSON file")
    parser.add_argument("--third-party", type=str, default=None, help="Optional path to Third-Party Claim JSON file")
    
    # Execution options
    parser.add_argument("--provider", type=str, default=None, choices=["gemini", "openai", "mock"],
                        help="Override LLM provider (defaults to LLM_PROVIDER env var or config)")
    parser.add_argument("--rework-count", type=int, default=0, help="Simulate rework attempt number (default 0)")
    parser.add_argument("--json", action="store_true", help="Output only the raw extracted JSON")
    parser.add_argument("--output", "-o", type=str, default=None, help="Save extracted JSON to specified file")

    return parser.parse_args()


def load_file(path_str: str) -> Dict[str, Any]:
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p.resolve()}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def print_formatted_extraction(result: ExtractionResult, meta: Dict[str, Any]):
    line = "=" * 78
    subline = "-" * 78
    
    print(line)
    print(f"CASEFILE EXTRACTOR NODE OUTPUT  |  Claim ID: {result.claim_id}")
    print(line)
    
    # Incident Facts
    print("\n📍 INCIDENT DETAILS")
    print(f"  Date / Time:     {result.incident_date}  {result.incident_time or '(Time not reported)'}")
    print(f"  Location:        {result.incident_location}")
    print(f"  Factual Summary: {result.incident_summary}")
    if result.police_report_filed:
        print(f"  Police Report:   Filed ({result.police_report_number or 'No report #'}) - {result.police_agency_or_officer or 'Agency not specified'}")
    else:
        print("  Police Report:   None filed")
    if result.other_party_involved:
        print(f"  Other Party:     {result.other_party_details or 'Involved'}")
    else:
        print("  Other Party:     Single-vehicle accident")

    # Vehicle Profile
    print("\n🚗 VEHICLE PROFILE")
    print(f"  Vehicle:         {result.vehicle_year} {result.vehicle_make} {result.vehicle_model}")
    print(f"  VIN:             {result.vehicle_vin}")
    print(f"  License Plate:   {result.vehicle_license_plate or 'N/A'}")
    print(f"  Odometer:        {result.vehicle_mileage:,} miles" if result.vehicle_mileage else "  Odometer:        N/A")
    print(f"  Drivable:        {'Yes (Drivable)' if result.is_drivable else 'No (Towed / Non-drivable)'}")

    # Driver Narrative Findings
    print("\n💥 REPORTED DAMAGE & INJURIES (FNOL NARRATIVE)")
    print(f"  Damage Areas:    {', '.join(result.reported_damage_areas) if result.reported_damage_areas else 'None stated'}")
    if result.injuries_reported:
        print(f"  Injuries:        YES - {result.injuries_summary or 'Injury reported'}")
    else:
        print("  Injuries:        None reported")

    # Repair Estimate
    print("\n🔧 REPAIR ESTIMATE AUDIT")
    print(f"  Shop / Facility: {result.repair_facility_name} (Tax ID: {result.repair_facility_tax_id or 'N/A'})")
    print(f"  Estimate Date:   {result.estimate_date}")
    print(f"  Parts Total:     ${result.total_parts_cost:>10,.2f}")
    print(f"  Labor Total:     ${result.total_labor_cost:>10,.2f}")
    print(f"  Additional / Tax:${result.total_additional_costs:>10,.2f}")
    print(f"  GRAND TOTAL:     ${result.claimed_grand_total:>10,.2f}")

    # Itemized Repairs Table
    if result.itemized_repairs:
        print(f"\n📋 ITEMIZED REPAIR OPERATIONS ({len(result.itemized_repairs)} items)")
        print(f"  {'Category':<16} {'Part Type':<11} {'Hours':<7} {'Amount':<10} {'Description'}")
        print(f"  {'-'*15} {'-'*10} {'-'*6} {'-'*9} {'-'*34}")
        for item in result.itemized_repairs:
            hrs_str = f"{item.labor_hours:.1f} hrs" if item.labor_hours is not None else "-"
            pt_str = item.part_type or "-"
            cat_str = item.category.replace("_", " ").title()
            print(f"  {cat_str:<16} {pt_str:<11} {hrs_str:<7} ${item.amount:>8,.2f}  {item.description}")
    else:
        print("\n📋 ITEMIZED REPAIR OPERATIONS: None extracted")

    # Auxiliary Documents
    has_aux = any([result.rental_receipt, result.medical_bills, result.third_party_claim])
    if has_aux:
        print("\n📎 AUXILIARY COVERAGE DOCUMENTS")
        if result.rental_receipt:
            rr = result.rental_receipt
            print(f"  [Rental Car Receipt]")
            print(f"    Agency:       {rr.rental_agency} (Invoice: {rr.invoice_number or 'N/A'})")
            print(f"    Dates:        {rr.start_date} to {rr.end_date} ({rr.days_billed} days @ ${rr.daily_rate:.2f}/day)")
            print(f"    Total Billed: ${rr.total_charged:,.2f}")
        if result.medical_bills:
            print(f"  [Medical Bills - {len(result.medical_bills)} Record(s)]")
            for i, mb in enumerate(result.medical_bills, 1):
                print(f"    Bill #{i}:      ${mb.total_billed:,.2f} from {mb.provider_name}")
                print(f"                   Patient: {mb.patient_name} | DOS: {mb.date_of_service}")
                print(f"                   Treatment: {mb.diagnosis_or_treatment}")
        if result.third_party_claim:
            tp = result.third_party_claim
            print(f"  [Third-Party Claim Demand]")
            print(f"    Claimant:     {tp.claimant_name} (Vehicle: {tp.vehicle_damaged or 'N/A'})")
            print(f"    Property Dam: ${tp.property_damage_claimed:,.2f}")
            print(f"    Injury Claim: ${tp.bodily_injury_claimed:,.2f}")
            print(f"    Demand:       {tp.demand_summary}")

    # Tracing & Handoff Summary
    print("\n" + subline)
    print("📊 EXECUTION METRICS")
    print(f"  Tokens Used:     {meta.get('tokens', 0):,}")
    print(f"  Call Cost:       ${meta.get('cost_usd', 0.0):.4f}")
    if meta.get("handoff"):
        h = meta["handoff"]
        print(f"  Handoff Action:  {h.source_node.upper()} -> {h.target_node.upper()} [{h.action}]")
        print(f"  Handoff Summary: {h.summary}")
    print(line + "\n")


def main():
    args = parse_args()

    # Configure provider if requested
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
        provider_name = args.provider
    else:
        provider_name = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)

    # 1. Resolve Document Sources
    fnol_data = None
    estimate_data = None
    rental_data = None
    medical_data = None
    third_party_data = None
    claim_id_label = ""

    if args.fnol and args.estimate:
        # Custom input files
        fnol_data = load_file(args.fnol)
        estimate_data = load_file(args.estimate)
        if args.rental:
            rental_data = load_file(args.rental)
        if args.medical:
            medical_data = load_file(args.medical)
        if args.third_party:
            third_party_data = load_file(args.third_party)
        
        claim_id_label = (
            fnol_data.get("intake_header", {}).get("claim_id")
            or fnol_data.get("claim_id")
            or "CUSTOM_CLAIM"
        )
    elif args.claim_id:
        # Load from CaseFile data store
        store = ClaimStore()
        cid = args.claim_id.replace("claim_", "").replace("CLM-2026-00", "")
        mapping = {"00147": "001", "00203": "002", "00251": "003", "00278": "004", "00299": "005"}
        claim_num = mapping.get(cid, cid)

        try:
            (
                fnol_data,
                estimate_data,
                _,  # policy_raw not needed for extraction
                rental_data,
                medical_data,
                third_party_data
            ) = store.load_claim_package(claim_num)
        except FileNotFoundError as e:
            available = store.list_available_claims()
            print(f"[Error] {e}", file=sys.stderr)
            print(f"Available claims in data dir: {available}", file=sys.stderr)
            sys.exit(1)

        claim_id_label = (
            fnol_data.get("intake_header", {}).get("claim_id")
            or fnol_data.get("claim_id")
            or f"claim_{claim_num}"
        )
    else:
        # Default to claim 001 if nothing passed
        store = ClaimStore()
        (
            fnol_data,
            estimate_data,
            _,
            rental_data,
            medical_data,
            third_party_data
        ) = store.load_claim_package("001")
        claim_id_label = "CLM-2026-00147"

    # 2. Build Minimal ClaimState for Extractor Node
    state: ClaimState = {
        "claim_id": claim_id_label,
        "run_id": "test_extractor_run",
        "thread_id": f"thread_{claim_id_label}",
        "fnol_raw": fnol_data,
        "estimate_raw": estimate_data,
        "policy_raw": {},
        "rental_raw": rental_data,
        "medical_raw": medical_data,
        "third_party_raw": third_party_data,
        "extraction": None,
        "investigation": None,
        "review": None,
        "human_decision": None,
        "current_phase": "intake",
        "step_count": 0,
        "rework_count": args.rework_count,
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

    # 3. Execute Extractor Node in Isolation
    if not args.json:
        print(f"\nRunning Extractor Node on {claim_id_label} [Provider: {provider_name}]...")

    output_state = extractor_node(state)
    result: ExtractionResult = output_state["extraction"]

    # Gather metrics
    meta = {
        "tokens": output_state.get("total_tokens", 0),
        "cost_usd": output_state.get("total_cost_usd", 0.0),
        "handoff": output_state.get("handoff_history", [None])[-1] if output_state.get("handoff_history") else None
    }

    # 4. Handle Output
    if args.json:
        # Raw JSON output
        json_output = json.dumps(result.model_dump(), indent=2, default=str)
        print(json_output)
    else:
        # Formatted visual output
        print_formatted_extraction(result, meta)

    # 5. Optionally save to file
    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(result.model_dump(), indent=2, default=str))
        if not args.json:
            print(f"Extracted output saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
