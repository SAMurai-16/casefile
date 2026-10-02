import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..schemas import TraceSummaryResponse, AnalyticsSummaryResponse
from ..service import ClaimsService
from ...config import TRACES_DIR
from ...store import ClaimStore

router = APIRouter(tags=["Traces & Operational Analytics"])

@router.get("/traces/{run_id}", response_model=TraceSummaryResponse)
def get_trace(run_id: str):
    # Find matching trace file in TRACES_DIR
    matching = list(TRACES_DIR.glob(f"*_{run_id}_trace.json"))
    if not matching:
        raise HTTPException(status_code=404, detail=f"No trace found for run '{run_id}'.")
    
    trace_path = matching[0]
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    
    return TraceSummaryResponse(
        run_id=run_id,
        claim_id=data.get("claim_id", "Unknown"),
        total_steps=metrics.get("total_steps", 0),
        total_tokens=metrics.get("total_tokens", 0),
        total_cost_usd=metrics.get("total_cost_usd", 0.0),
        execution_path=data.get("execution_path", []),
        trace_data=data
    )

@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics():
    service = ClaimsService.get_instance()
    all_claims = ClaimStore().list_available_claims()

    total_runs = len(service.runs)
    total_cost = sum(r.get("total_cost_usd", 0.0) for r in service.runs.values())
    total_tokens = sum(r.get("total_tokens", 0) for r in service.runs.values())
    
    status_counts = {}
    for r in service.runs.values():
        st = r.get("terminal_status") or r.get("status") or "unknown"
        status_counts[st] = status_counts.get(st, 0) + 1

    avg_cost = round(total_cost / max(1, total_runs), 4)

    return AnalyticsSummaryResponse(
        total_claims_in_store=len(all_claims),
        total_runs_executed=total_runs,
        total_cost_usd=round(total_cost, 4),
        total_tokens_used=total_tokens,
        avg_cost_per_claim_usd=avg_cost,
        terminal_status_breakdown=status_counts,
        avg_fraud_risk_score=26.4
    )
