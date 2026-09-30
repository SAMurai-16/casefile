import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import uuid
from casefile.store import ClaimStore, get_checkpointer
from casefile.graph import build_claims_graph
from casefile.tracing import TraceLogger
from casefile.schema import ClaimState
from langgraph.types import Command

def run_claim(claim_id_input: str, auto_approve: bool = True, provider: str = None):
    store = ClaimStore()
    
    # Normalize ID: "001" or "CLM-2026-00147"
    claim_num = claim_id_input.replace("claim_", "").replace("CLM-2026-00", "")
    if len(claim_num) == 5:
        mapping = {"00147": "001", "00203": "002", "00251": "003", "00278": "004", "00299": "005"}
        claim_num = mapping.get(claim_num, claim_num)
        
    fnol_raw, est_raw, pol_raw, rental_raw, medical_raw, third_party_raw = store.load_claim_package(claim_num)
    canonical_claim_id = fnol_raw.get("intake_header", {}).get("claim_id") or fnol_raw.get("claim_id")
    
    run_id = str(uuid.uuid4())[:8]
    thread_id = f"thread_{canonical_claim_id}_{run_id}"
    
    # List attached documents
    attached = ["FNOL Narrative", "Repair Estimate", "Policy Record"]
    if rental_raw:
        attached.append(f"Rental Invoice ({rental_raw.get('rental_agency', {}).get('name', 'Rental Agency')})")
    if medical_raw:
        attached.append(f"Medical Bill ({medical_raw.get('billing_provider', {}).get('clinic_name', 'Medical Provider')})")
    if third_party_raw:
        attached.append(f"Third-Party Demand ({third_party_raw.get('third_party_claimant', {}).get('name', 'Third Party')})")

    print("=" * 75)
    print(f"CASEFILE: Processing Claim {canonical_claim_id} [Run: {run_id}]")
    print(f"Channel:  {fnol_raw.get('intake_header', {}).get('channel', 'Standard')}")
    print(f"Attached: {', '.join(attached)}")
    print("=" * 75)
    
    checkpointer = get_checkpointer("memory")
    graph = build_claims_graph(checkpointer=checkpointer)
    logger = TraceLogger(claim_id=canonical_claim_id, run_id=run_id)
    
    initial_state: ClaimState = {
        "claim_id": canonical_claim_id,
        "run_id": run_id,
        "thread_id": thread_id,
        "fnol_raw": fnol_raw,
        "estimate_raw": est_raw,
        "policy_raw": pol_raw,
        "rental_raw": rental_raw,
        "medical_raw": medical_raw,
        "third_party_raw": third_party_raw,
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
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Stream node execution
    for event in graph.stream(initial_state, config=config):
        for node_name, node_update in event.items():
            if node_name == "__interrupt__":
                continue
            step = node_update.get("step_count", 0)
            tokens = node_update.get("total_tokens", 0)
            cost = node_update.get("total_cost_usd", 0.0)
            logger.record_node_entry(node_name, step, tokens, cost)
            print(f"  --> Step {step:2d} | Node: {node_name:<14} | Phase: {node_update.get('current_phase', ''):<12} | Cost: ${cost:.4f}")
            
    # Check if graph paused at human approval gate
    state_snapshot = graph.get_state(config)
    if state_snapshot.next and "human_gate" in state_snapshot.next:
        investigation_res = state_snapshot.values.get("investigation")
        review_res = state_snapshot.values.get("review")
        proposed = review_res.proposed_payout_amount if review_res else 0.0
        breakdown = review_res.payout_breakdown if review_res and review_res.payout_breakdown else {}
        
        print("\n" + "-" * 75)
        print("HUMAN APPROVAL GATE: Multi-Line Payout Authorization Required")
        if investigation_res:
            acv_str = f"${investigation_res.actual_cash_value:,.2f}" if investigation_res.actual_cash_value else "N/A"
            ratio_str = f"{investigation_res.repair_to_acv_ratio * 100:.1f}%" if investigation_res.repair_to_acv_ratio else "N/A"
            print(f"  Risk Profile:       Level={investigation_res.fraud_risk_level.upper()} (Score: {investigation_res.fraud_risk_score}/100) | ACV: {acv_str} (Repair/ACV: {ratio_str})")
            if investigation_res.is_total_loss_candidate:
                print("  🚨 TOTAL LOSS CANDIDATE: Repair cost exceeds statutory total loss threshold.")

        if investigation_res and (investigation_res.endorsements_validated or investigation_res.clause_audit_notes or investigation_res.applied_exclusions):
            print("  Policy Contract & Clause Audit:")
            if investigation_res.endorsements_validated:
                for end in investigation_res.endorsements_validated:
                    print(f"    📜 Active Endorsement: {end}")
            if investigation_res.applied_exclusions:
                for excl in investigation_res.applied_exclusions:
                    print(f"    🚫 Exclusion Triggered: {excl}")
            if investigation_res.clause_audit_notes:
                for note in investigation_res.clause_audit_notes:
                    print(f"    ⚖️  Contract Clause:    {note}")

        if review_res and review_res.discrepancy_details:
            print("  Discrepancies Audited:")
            for disc in review_res.discrepancy_details:
                print(f"    ⚠️  {disc}")

        print("\n  Itemized Payout Breakdown:")
        for line_item, amt in breakdown.items():
            print(f"    • {line_item.replace('_', ' ').title():<25}: ${amt:>10,.2f}")
        print(f"    {'TOTAL PROPOSED SETTLEMENT':<27}: ${proposed:>10,.2f}")
        
        if review_res and review_res.liability_warning:
            print(f"\n  ⚠️  LIABILITY WARNING: {review_res.liability_warning}")
            
        print(f"\n  Justification: {review_res.justification if review_res else 'N/A'}")
        
        if auto_approve:
            print("  [Auto-Approve Flag Active] -> Adjuster approves proposed payout.")
            human_response = {
                "approver_id": "senior_adjuster_auto",
                "action": "approve",
                "authorized_amount": proposed,
                "comments": "Approved under regional multi-line authority guidelines."
            }
        else:
            choice = input("\n  Decision [A]pprove / [R]eject / [E]xit: ").strip().lower()
            if choice == "r":
                human_response = {
                    "approver_id": "claims_examiner_manual",
                    "action": "reject",
                    "authorized_amount": 0.0,
                    "comments": "Rejected by examiner."
                }
            else:
                human_response = {
                    "approver_id": "claims_examiner_manual",
                    "action": "approve",
                    "authorized_amount": proposed,
                    "comments": "Approved by examiner."
                }
        
        # Resume the graph past the gate
        for event in graph.stream(Command(resume=human_response), config=config):
            for node_name, node_update in event.items():
                step = node_update.get("step_count", 0)
                tokens = node_update.get("total_tokens", 0)
                cost = node_update.get("total_cost_usd", 0.0)
                logger.record_node_entry(node_name, step, tokens, cost)
                print(f"  --> Step {step:2d} | Node: {node_name:<14} | Phase: {node_update.get('current_phase', ''):<12} | Cost: ${cost:.4f}")

    final_snapshot = graph.get_state(config)
    final_state = final_snapshot.values
    trace_path = logger.export(final_state)
    
    print("\n" + "=" * 75)
    print(f"FINAL SETTLEMENT SUMMARY: {canonical_claim_id}")
    print(f"  Status:             {(final_state.get('terminal_status') or 'UNKNOWN').upper()}")
    print(f"  Final Payout:       ${final_state.get('final_payout_amount', 0.0) or 0.0:,.2f}")
    if final_state.get("payout_breakdown"):
        print("  Settled Lines:")
        for line, amt in final_state["payout_breakdown"].items():
            print(f"    - {line.replace('_', ' ').title():<22}: ${amt:>9,.2f}")
    print(f"  Total Steps:        {final_state.get('step_count', 0)}")
    print(f"  Total Tokens:       {final_state.get('total_tokens', 0):,}")
    print(f"  Total Cost:         ${final_state.get('total_cost_usd', 0.0):.4f}")
    print(f"  Execution Path:     {' -> '.join(logger.node_path)}")
    print(f"  Trace File:         {trace_path}")
    print("=" * 75 + "\n")
    return final_state

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CaseFile orchestration on a single claim package.")
    parser.add_argument("claim_id", nargs="?", default="001", help="Claim number (001, 002, 003, 004, 005)")
    parser.add_argument("--interactive", action="store_true", help="Prompt human at approval gate")
    args = parser.parse_args()
    
    run_claim(args.claim_id, auto_approve=not args.interactive)
