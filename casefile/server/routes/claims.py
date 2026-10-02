import asyncio
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from ..schemas import (
    ClaimListResponse,
    ClaimDetailResponse,
    ClaimListItem,
    ClaimIngestRequest,
    ClaimIngestResponse,
    RunClaimRequest,
    RunClaimResponse,
    RunStatusResponse,
    ThreadStateResponse,
)
from ..service import ClaimsService

router = APIRouter(prefix="/claims", tags=["Claims & Agent Runs"])

@router.get("", response_model=ClaimListResponse)
def list_claims():
    service = ClaimsService.get_instance()
    items = service.list_claims()
    return ClaimListResponse(claims=[ClaimListItem(**it) for it in items], total=len(items))

@router.post("", response_model=ClaimIngestResponse, status_code=201)
def ingest_claim(req: ClaimIngestRequest):
    service = ClaimsService.get_instance()
    try:
        res = service.ingest_claim(req)
        return ClaimIngestResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to ingest claim: {str(e)}")

@router.get("/{claim_id}", response_model=ClaimDetailResponse)
def get_claim(claim_id: str):
    service = ClaimsService.get_instance()
    try:
        detail = service.get_claim_detail(claim_id)
        return ClaimDetailResponse(**detail)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{claim_id}/run", response_model=RunClaimResponse)
def run_claim(claim_id: str, req: Optional[RunClaimRequest] = None):
    if req is None:
        req = RunClaimRequest()
    service = ClaimsService.get_instance()
    try:
        res = service.launch_claim_run(
            claim_id=claim_id,
            auto_approve=req.auto_approve,
            thread_id=req.thread_id
        )
        return RunClaimResponse(**res)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{claim_id}/runs/{run_id}/status", response_model=RunStatusResponse)
def get_run_status(claim_id: str, run_id: str):
    service = ClaimsService.get_instance()
    run = service.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return RunStatusResponse(**run)

@router.get("/{claim_id}/runs/{run_id}/state", response_model=ThreadStateResponse)
def get_run_state(claim_id: str, run_id: str):
    service = ClaimsService.get_instance()
    state = service.get_run_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found or has no state.")
    return ThreadStateResponse(**state)

@router.get("/{claim_id}/runs/{run_id}/stream")
async def stream_run_events(claim_id: str, run_id: str, request: Request):
    service = ClaimsService.get_instance()
    run = service.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    async def event_generator():
        q = service.register_event_queue(run_id)
        try:
            # First send initial connection event with current state
            initial_event = {
                "event": "connected",
                "data": {
                    "run_id": run_id,
                    "claim_id": claim_id,
                    "status": run.get("status"),
                    "current_phase": run.get("current_phase")
                }
            }
            yield f"event: {initial_event['event']}\ndata: {json.dumps(initial_event['data'])}\n\n"

            while True:
                # Disconnect guard
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                    if event["event"] == "end":
                        break
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield ": ping\n\n"
        finally:
            service.unregister_event_queue(run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
