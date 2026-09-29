import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from scripts.run_single_claim import run_claim

def test_claim_001_multi_coverage_approval_path():
    """Verify that Claim 001 settles vehicle repair, rental reimbursement, and MedPay."""
    state = run_claim("001", auto_approve=True)
    assert state["terminal_status"] == "approved"
    assert state["final_payout_amount"] == 4233.79
    
    breakdown = state["payout_breakdown"]
    assert breakdown is not None
    assert breakdown.get("vehicle_repair") == 3517.79
    assert breakdown.get("rental_car") == 336.00
    assert breakdown.get("medical_payments") == 380.00
    assert state["step_count"] <= 10

def test_claim_002_partial_approval_path():
    state = run_claim("002", auto_approve=True)
    assert state["terminal_status"] == "approved"
    assert state["final_payout_amount"] == 9000.00  # Capped at $10k limit - $1k deductible
    assert state["payout_breakdown"].get("vehicle_repair") == 9000.00

def test_claim_003_auto_approval_path():
    state = run_claim("003", auto_approve=True)
    assert state["terminal_status"] == "approved"
    assert state["final_payout_amount"] == 504.86

def test_claim_004_siu_escalation_path():
    state = run_claim("004", auto_approve=True)
    assert state["terminal_status"] == "escalated_siu"
    assert state["final_payout_amount"] == 0.0

def test_claim_005_lapsed_denial_fast_path():
    state = run_claim("005", auto_approve=True)
    assert state["terminal_status"] == "denied"
    assert state["final_payout_amount"] == 0.0
    # Fast path: short-circuits in 5 steps without reviewer
    assert state["step_count"] == 5
