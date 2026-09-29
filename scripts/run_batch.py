import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import glob
from casefile.store import ClaimStore
from scripts.run_single_claim import run_claim
from casefile.config import TRACES_DIR

def run_batch():
    """Executes all 30 claims and collects node-path traces for the ship gate."""
    store = ClaimStore()
    available = store.list_available_claims()
    print("=" * 80)
    print(f"CASEFILE BATCH EXECUTION: Running {len(available)} Claims")
    print("=" * 80)
    
    results = []
    
    for c_id in available:
        print(f"\n>>> Running Claim {c_id}...")
        try:
            state = run_claim(c_id, auto_approve=True)
            results.append({
                "claim": c_id,
                "status": state.get("terminal_status", "UNKNOWN"),
                "payout": state.get("final_payout_amount", 0.0) or 0.0,
                "steps": state.get("step_count", 0),
                "tokens": state.get("total_tokens", 0),
                "cost": state.get("total_cost_usd", 0.0),
            })
        except Exception as e:
            print(f"ERROR on claim {c_id}: {e}")
            results.append({
                "claim": c_id,
                "status": "ERROR",
                "payout": 0.0,
                "steps": 0,
                "tokens": 0,
                "cost": 0.0
            })

    # Summary Table
    print("\n" + "=" * 80)
    print(f"{'CLAIM':<8} | {'STATUS':<15} | {'PAYOUT':<12} | {'STEPS':<6} | {'TOKENS':<8} | {'COST ($)':<8}")
    print("-" * 80)
    total_cost = 0.0
    for r in results:
        total_cost += r["cost"]
        print(f"{r['claim']:<8} | {r['status']:<15} | ${r['payout']:<11,.2f} | {r['steps']:<6} | {r['tokens']:<8} | ${r['cost']:<8.4f}")
    print("=" * 80)
    print(f"Batch Complete. Total Claims: {len(results)} | Total Cost: ${total_cost:.4f}")
    
    traces_count = len(list(TRACES_DIR.glob("*_trace.json")))
    print(f"Verified {traces_count} recorded JSON trace files in {TRACES_DIR}")

if __name__ == "__main__":
    run_batch()
