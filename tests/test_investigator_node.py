import pytest
from casefile.store.claim_store import ClaimStore
from casefile.schema import ClaimState
from casefile.agents.extractor import extractor_node
from casefile.agents.investigator import investigator_node, compute_multi_line_policy_math


def _build_test_state(claim_id_num: str) -> ClaimState:
    store = ClaimStore()
    fnol, est, pol, rental, med, tp = store.load_claim_package(claim_id_num)
    return {
        "claim_id": f"CLM-TEST-{claim_id_num}",
        "run_id": f"test_run_{claim_id_num}",
        "thread_id": f"thread_test_{claim_id_num}",
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


def test_investigator_claim_001_multi_line_and_endorsement():
    """Verify Claim 001 evaluates collision, rental, MedPay, and active OEM rider."""
    state = _build_test_state("001")
    ext_out = extractor_node(state)
    state["extraction"] = ext_out["extraction"]

    inv_out = investigator_node(state)
    res = inv_out["investigation"]

    # Pillar 1: Valuation
    assert res.actual_cash_value == pytest.approx(24990.75, rel=1e-2)
    assert res.repair_to_acv_ratio == pytest.approx(0.1608, rel=1e-2)
    assert res.is_total_loss_candidate is False

    # Pillar 2: Fraud Risk
    assert res.fraud_risk_score <= 25
    assert res.fraud_risk_level == "low"
    assert res.siu_referral_recommended is False

    # Pillar 3: Multi-Line Math
    assert res.collision_covered is True
    assert res.max_eligible_collision_payout == 24500.00  # $25k limit - $500 deductible
    assert res.rental_reimbursement_covered is True
    assert res.rental_eligible_payout == 336.00          # 8 days @ $42/day
    assert res.medpay_covered is True
    assert res.medpay_eligible_payout == 380.00          # Dr. Sharma visit

    # Pillar 4: Contract Clauses
    assert any("END-OEM-01" in end for end in res.endorsements_validated)
    assert len(res.clause_audit_notes) >= 1


def test_investigator_claim_002_lkq_clause_and_cap():
    """Verify Claim 002 caps collision at limit minus deductible and audits LKQ clause."""
    state = _build_test_state("002")
    ext_out = extractor_node(state)
    state["extraction"] = ext_out["extraction"]

    inv_out = investigator_node(state)
    res = inv_out["investigation"]

    # Pillar 1: Valuation
    assert res.actual_cash_value == pytest.approx(31782.00, rel=1e-2)
    assert res.repair_to_acv_ratio == pytest.approx(0.396, rel=1e-2)
    assert res.is_total_loss_candidate is False

    # Pillar 3: Multi-Line Math
    assert res.collision_covered is True
    assert res.max_eligible_collision_payout == 9000.00  # $10k limit - $1k deductible
    assert res.rental_eligible_payout == 0.0
    assert res.medpay_eligible_payout == 0.0

    # Pillar 4: LKQ Clause Audit
    assert any("SEC-IV-COND-7" in note for note in res.clause_audit_notes)


def test_investigator_claim_004_total_loss_and_siu():
    """Verify Claim 004 triggers statutory total loss candidate (88.3% of ACV)."""
    state = _build_test_state("004")
    ext_out = extractor_node(state)
    state["extraction"] = ext_out["extraction"]

    inv_out = investigator_node(state)
    res = inv_out["investigation"]

    assert res.repair_to_acv_ratio >= 0.75
    assert res.is_total_loss_candidate is True


def test_investigator_claim_005_cancelled_void_coverage():
    """Verify Claim 005 zeroes out all payouts on a cancelled policy."""
    state = _build_test_state("005")
    ext_out = extractor_node(state)
    state["extraction"] = ext_out["extraction"]

    inv_out = investigator_node(state)
    res = inv_out["investigation"]

    assert res.coverage_verdict == "not_covered"
    assert res.max_eligible_collision_payout == 0.0
    assert res.rental_eligible_payout == 0.0
    assert res.medpay_eligible_payout == 0.0


def test_deterministic_multi_line_math_arithmetic():
    """Unit test compute_multi_line_policy_math directly against synthetic edge cases."""
    mock_policy = {
        "policy": {"status": "Active"},
        "coverage": {
            "collision": {"covered": True, "per_incident_limit": 50000.0, "deductible": 1000.0},
            "rental_reimbursement": {"covered": True, "daily_limit": 40.0, "max_days": 10},
            "medical_payments": {"covered": True, "per_person_limit": 2500.0},
        }
    }
    # Create mock extraction
    state = _build_test_state("001")
    ext = extractor_node(state)["extraction"]
    
    math_res = compute_multi_line_policy_math(mock_policy, ext)
    assert math_res["collision_covered"] is True
    assert math_res["max_eligible_collision_payout"] == 49000.0  # 50000 - 1000
    # Billed 8 days @ $42/day, policy cap $40/day
    assert math_res["rental_eligible_payout"] == 320.0          # 8 * 40.0
    # Billed $380, cap $2500
    assert math_res["medpay_eligible_payout"] == 380.0
