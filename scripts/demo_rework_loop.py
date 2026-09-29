from casefile.store import ClaimStore, get_checkpointer
from casefile.graph import build_claims_graph
from casefile.schema import ClaimState
from casefile.tracing import TraceLogger
from langgraph.types import Command
import uuid

def demo_rework_cycle():
    """
    Demonstrates Ship Gate Requirement 3:
    'The reviewer sends work back at least once and the graph still terminates'
    """
    print("=" * 70)
    print("DEMO: Reviewer Rework Loop & Safe Graph Termination")
    print("=" * 70)
    
    store = ClaimStore()
    fnol, est, pol, rental, med, tp = store.load_claim_package("001")
    claim_id = "CLM-REWORK-001"
    run_id = str(uuid.uuid4())[:8]
    thread_id = f"thread_rework_{run_id}"
    
    checkpointer = get_checkpointer("memory")
    graph = build_claims_graph(checkpointer=checkpointer)
    logger = TraceLogger(claim_id=claim_id, run_id=run_id)
    
    initial_state: ClaimState = {
        "claim_id": claim_id,
        "run_id": run_id,
        "thread_id": thread_id,
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
    
    config = {"configurable": {"thread_id": thread_id}}
    
    for event in graph.stream(initial_state, config=config):
        for node_name, node_update in event.items():
            if node_name == "__interrupt__":
                continue
            step = node_update.get("step_count", 0)
            phase = node_update.get("current_phase", "")
            rework_c = node_update.get("rework_count", 0)
            print(f"  Step {step:2d} | Node: {node_name:<14} | Phase: {phase:<12} | Rework Count: {rework_c}")

    # If halted at human gate after rework completes
    snapshot = graph.get_state(config)
    if snapshot.next and "human_gate" in snapshot.next:
        print("\n  >>> Human Gate reached after successful rework pass!")
        resume_cmd = Command(resume={
            "approver_id": "senior_adjuster",
            "action": "approve",
            "authorized_amount": 3517.79,
            "comments": "Approved post-rework."
        })
        for event in graph.stream(resume_cmd, config=config):
            for node_name, node_update in event.items():
                if node_name != "__interrupt__":
                    step = node_update.get("step_count", 0)
                    phase = node_update.get("current_phase", "")
                    print(f"  Step {step:2d} | Node: {node_name:<14} | Phase: {phase:<12}")

    final_state = graph.get_state(config).values
    print("\n" + "=" * 70)
    print("REWORK DEMO TERMINAL AUDIT:")
    print(f"  Final Status:        {final_state.get('terminal_status')}")
    print(f"  Rework Count:        {final_state.get('rework_count')} (Required >= 1)")
    print(f"  Total Steps Taken:   {final_state.get('step_count')}")
    print(f"  Graph Terminated:    {final_state.get('current_phase') == 'terminated'}")
    print("=" * 70)
    assert final_state.get("rework_count") >= 1, "Rework was not recorded in state!"
    assert final_state.get("current_phase") == "terminated", "Graph failed to terminate after rework!"
    print("SUCCESS: Graph looped through rework and cleanly terminated under guard rails.\n")

if __name__ == "__main__":
    demo_rework_cycle()
