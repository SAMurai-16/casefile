import pytest
from casefile.agents.supervisor import supervisor_node
from casefile.schema import ClaimState, ReviewResult
from casefile.config import COST_CEILING_USD, MAX_STEPS, MAX_REWORK_COUNT

def test_cost_ceiling_guard():
    """Verify that breaching the dollar budget terminates the graph immediately."""
    state: ClaimState = {
        "claim_id": "CLM-GUARD-TEST",
        "run_id": "r1",
        "thread_id": "t1",
        "fnol_raw": {},
        "estimate_raw": {},
        "policy_raw": {},
        "extraction": None,
        "investigation": None,
        "review": None,
        "human_decision": None,
        "current_phase": "intake",
        "step_count": 3,
        "rework_count": 0,
        "handoff_history": [],
        "total_tokens": 1000,
        "total_cost_usd": COST_CEILING_USD + 0.05,  # Breached!
        "budget_exceeded": False,
        "max_steps_exceeded": False,
        "terminal_status": None,
        "final_payout_amount": None,
        "settlement_summary": None,
    }
    
    update = supervisor_node(state)
    assert update["current_phase"] == "terminated"
    assert update["terminal_status"] == "budget_terminated"
    assert update["budget_exceeded"] is True

def test_max_steps_loop_guard():
    """Verify that reaching max steps terminates the graph and prevents infinite recursion."""
    state: ClaimState = {
        "claim_id": "CLM-GUARD-TEST",
        "run_id": "r1",
        "thread_id": "t1",
        "fnol_raw": {},
        "estimate_raw": {},
        "policy_raw": {},
        "extraction": None,
        "investigation": None,
        "review": None,
        "human_decision": None,
        "current_phase": "intake",
        "step_count": MAX_STEPS,  # At ceiling!
        "rework_count": 0,
        "handoff_history": [],
        "total_tokens": 1000,
        "total_cost_usd": 0.05,
        "budget_exceeded": False,
        "max_steps_exceeded": False,
        "terminal_status": None,
        "final_payout_amount": None,
        "settlement_summary": None,
    }
    
    update = supervisor_node(state)
    assert update["current_phase"] == "terminated"
    assert update["terminal_status"] == "step_limit_terminated"
    assert update["max_steps_exceeded"] is True
