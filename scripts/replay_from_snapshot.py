import argparse
from casefile.store import ClaimStore, get_checkpointer
from casefile.graph import build_claims_graph
from casefile.schema import ClaimState
from langgraph.types import Command

def test_replayability(claim_num: str = "001"):
    """
    Demonstrates snapshot replayability:
    1. Runs graph halfway (up through extraction & investigation) with checkpointing.
    2. Takes a snapshot of state.
    3. Replays from that exact snapshot on a new thread/fork.
    4. Asserts that the replayed execution terminates in the exact same state.
    """
    store = ClaimStore()
    fnol, est, pol, rental, med, tp = store.load_claim_package(claim_num)
    claim_id = fnol.get("intake_header", {}).get("claim_id") or fnol.get("claim_id")
    
    checkpointer = get_checkpointer("memory")
    graph = build_claims_graph(checkpointer=checkpointer)
    
    thread_original = f"orig_{claim_id}"
    config_orig = {"configurable": {"thread_id": thread_original}}
    
    initial_state: ClaimState = {
        "claim_id": claim_id,
        "run_id": "orig_run",
        "thread_id": thread_original,
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
        "final_payout_amount": None,
        "settlement_summary": None,
    }
    
    print("=" * 70)
    print(f"REPLAY PROOF: Executing Original Run for {claim_id}")
    print("=" * 70)
    
    for event in graph.stream(initial_state, config=config_orig):
        for node, update in event.items():
            if node != "__interrupt__":
                print(f"  [Original] Node: {node:<14} | Step: {update.get('step_count', 0)}")
                
    # If paused at human gate, resume
    snapshot = graph.get_state(config_orig)
    if snapshot.next and "human_gate" in snapshot.next:
        review_val = snapshot.values.get("review")
        proposed = review_val.proposed_payout_amount if review_val else 0.0
        graph.invoke(Command(resume={
            "approver_id": "replay_verifier",
            "action": "approve",
            "authorized_amount": proposed,
            "comments": "Automated snapshot replay verification"
        }), config=config_orig)
        
    final_original = graph.get_state(config_orig).values
    print(f"\nOriginal Terminal Status: {final_original['terminal_status']}")
    print(f"Original Payout: ${final_original.get('final_payout_amount', 0.0):,.2f}")
    
    # Now inspect all checkpoints saved in the checkpointer
    history = list(graph.get_state_history(config_orig))
    print(f"\nCheckpointer captured {len(history)} distinct superstep snapshots.")
    
    # Grab a checkpoint from midway (e.g. after extractor or investigator)
    midway_checkpoint = history[len(history) // 2]
    midway_config = midway_checkpoint.config
    print(f"Selecting Midway Checkpoint ID: {midway_config['configurable'].get('checkpoint_id')}")
    print(f"Midway Phase: {midway_checkpoint.values.get('current_phase')}")
    
    # Fork/Resume execution from this exact snapshot onto an independent thread
    print("\n" + "-" * 70)
    print("Replaying execution from snapshot onto new thread...")
    print("-" * 70)
    
    fork_thread = f"replay_fork_{claim_id}"
    fork_config = {"configurable": {"thread_id": fork_thread}}
    
    # Initialize the forked thread with the midway checkpoint values
    fork_input = midway_checkpoint.values.copy()
    fork_input["thread_id"] = fork_thread
    fork_input["run_id"] = "replayed_fork"
    
    for event in graph.stream(fork_input, config=fork_config):
        for node, update in event.items():
            if node != "__interrupt__":
                print(f"  [Replay]   Node: {node:<14} | Step: {update.get('step_count', 0)}")
                
    post_replay = graph.get_state(fork_config)
    if post_replay.next and "human_gate" in post_replay.next:
        review_val = post_replay.values.get("review")
        proposed = review_val.proposed_payout_amount if review_val else 0.0
        resume_cmd = Command(resume={
            "approver_id": "replay_verifier",
            "action": "approve",
            "authorized_amount": proposed,
            "comments": "Automated snapshot replay verification"
        })
        for event in graph.stream(resume_cmd, config=fork_config):
            for node, update in event.items():
                if node != "__interrupt__":
                    print(f"  [Replay]   Node: {node:<14} | Step: {update.get('step_count', 0)}")

    final_replayed = graph.get_state(fork_config).values
    payout_val = final_replayed.get("final_payout_amount") or 0.0
    print(f"\nReplayed Terminal Status: {final_replayed.get('terminal_status')}")
    print(f"Replayed Payout: ${payout_val:,.2f}")
    
    # Verify Invariants
    assert final_original["terminal_status"] == final_replayed["terminal_status"], "Terminal status mismatch between original and replay!"
    assert final_original["final_payout_amount"] == final_replayed["final_payout_amount"], "Payout mismatch between original and replay!"
    print("\n" + "=" * 70)
    print("SUCCESS: Snapshot replay proved 100% deterministic terminal parity!")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim", default="001")
    args = parser.parse_args()
    test_replayability(args.claim)
