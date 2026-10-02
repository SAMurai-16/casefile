import pytest
import os
from starlette.testclient import TestClient

# Ensure mock LLM is used for tests
os.environ["LLM_PROVIDER"] = "mock"

from casefile.server.app import create_app
from casefile.server.service import ClaimsService

@pytest.fixture(scope="module")
def client():
    # Fresh app instance
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "CaseFile Multi-Agent Claims API"
    assert "endpoints" in data

def test_system_health_and_config(client):
    res = client.get("/api/v1/system/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    cfg = client.get("/api/v1/system/config")
    assert cfg.status_code == 200
    assert "llm_provider" in cfg.json()
    assert "cost_ceiling_guard_usd" in cfg.json()

def test_claims_listing_and_detail(client):
    res = client.get("/api/v1/claims")
    assert res.status_code == 200
    claims = res.json()["claims"]
    assert len(claims) > 0
    assert any("001" in c["claim_id"] for c in claims)

    # Detail test
    det = client.get("/api/v1/claims/001")
    assert det.status_code == 200
    assert "raw_documents" in det.json()
    assert "fnol" in det.json()["raw_documents"]

    # 404 test
    not_found = client.get("/api/v1/claims/non_existent_999")
    assert not_found.status_code == 404

def test_claim_run_and_human_approval_gate_lifecycle(client):
    # 1. Launch a run with manual approval required
    run_res = client.post("/api/v1/claims/001/run", json={"auto_approve": False})
    assert run_res.status_code == 200
    data = run_res.json()
    run_id = data["run_id"]
    thread_id = data["thread_id"]

    import time
    # Poll status until paused_at_gate
    for _ in range(50):
        st = client.get(f"/api/v1/claims/001/runs/{run_id}/status")
        assert st.status_code == 200
        if st.json()["status"] == "paused_at_gate":
            break
        time.sleep(0.1)

    status_data = client.get(f"/api/v1/claims/001/runs/{run_id}/status").json()
    assert status_data["is_paused_at_gate"] is True
    assert status_data["status"] == "paused_at_gate"

    # 2. Query pending approvals
    pending = client.get("/api/v1/approval-gate/pending")
    assert pending.status_code == 200
    pending_list = pending.json()
    matching_pending = [p for p in pending_list if p["thread_id"] == thread_id]
    assert len(matching_pending) == 1

    # 3. Inspect approval dossier
    dossier_res = client.get(f"/api/v1/approval-gate/{thread_id}")
    assert dossier_res.status_code == 200
    dossier = dossier_res.json()
    assert "fraud_risk_score" in dossier
    assert "itemized_payout_breakdown" in dossier
    assert dossier["total_proposed_payout"] > 0

    # 4. Submit human adjuster approval decision
    decision_payload = {
        "approver_id": "test_adjuster_007",
        "action": "approve",
        "authorized_amount": dossier["total_proposed_payout"],
        "comments": "Audited and approved via automated API test suite."
    }
    dec_res = client.post(f"/api/v1/approval-gate/{thread_id}/decision", json=decision_payload)
    assert dec_res.status_code == 200
    dec_data = dec_res.json()
    assert dec_data["action"] == "approve"
    assert dec_data["terminal_status"] == "approved"
    assert dec_data["final_payout_authorized"] == dossier["total_proposed_payout"]

    # 5. Check thread state snapshot and run state endpoint
    thread_state = client.get(f"/api/v1/threads/{thread_id}/state")
    assert thread_state.status_code == 200
    assert thread_state.json()["current_phase"] == "terminated"
    assert "extraction" in thread_state.json()["values"]

    run_state = client.get(f"/api/v1/claims/001/runs/{run_id}/state")
    assert run_state.status_code == 200
    assert run_state.json()["thread_id"] == thread_id
    assert "extraction" in run_state.json()["values"]
    assert "investigation" in run_state.json()["values"]

    # 6. Check thread history checkpoints
    hist = client.get(f"/api/v1/threads/{thread_id}/history")
    assert hist.status_code == 200
    assert hist.json()["total_checkpoints"] >= 4

def test_analytics_summary(client):
    res = client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert "total_claims_in_store" in data
    assert "total_runs_executed" in data

def test_sse_streaming_events(client):
    run_res = client.post("/api/v1/claims/002/run", json={"auto_approve": True})
    assert run_res.status_code == 200
    run_id = run_res.json()["run_id"]

    # Connect to stream
    with client.stream("GET", f"/api/v1/claims/002/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        events_received = []
        for line in response.iter_lines():
            if line.startswith("event: "):
                events_received.append(line.replace("event: ", "").strip())
            if len(events_received) >= 2 or "end" in events_received:
                break
        assert len(events_received) >= 1


def test_custom_claim_ingestion(client):
    test_claim_id = "test_custom_99"
    # Load sample data from claim 003
    det = client.get("/api/v1/claims/003").json()
    raw = det["raw_documents"]

    payload = {
        "claim_id": test_claim_id,
        "fnol_raw": raw["fnol"],
        "estimate_raw": raw["estimate"],
        "policy_raw": raw["policy"],
        "rental_raw": raw.get("rental"),
        "medical_raw": raw.get("medical"),
        "third_party_raw": raw.get("third_party")
    }

    # 1. Ingest custom claim
    ingest_res = client.post("/api/v1/claims", json=payload)
    assert ingest_res.status_code == 201
    assert ingest_res.json()["claim_id"] == test_claim_id

    # 2. Verify it is immediately visible in claims listing
    claims_list = client.get("/api/v1/claims").json()["claims"]
    assert any(c["claim_id"] == test_claim_id for c in claims_list)

    # 3. Verify get detail returns the uploaded documents
    det_res = client.get(f"/api/v1/claims/{test_claim_id}")
    assert det_res.status_code == 200
    assert det_res.json()["claim_id"] == test_claim_id

    # 4. Verify we can launch a run on the uploaded custom claim!
    run_res = client.post(f"/api/v1/claims/{test_claim_id}/run", json={"auto_approve": True})
    assert run_res.status_code == 200
    assert run_res.json()["status"] == "running"

    # Cleanup test files
    from casefile.config import DATA_DIR
    for f in DATA_DIR.glob(f"claim_{test_claim_id}_*"):
        f.unlink(missing_ok=True)
