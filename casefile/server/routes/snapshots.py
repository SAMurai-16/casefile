from fastapi import APIRouter, HTTPException
from ..schemas import (
    ThreadStateResponse,
    ThreadHistoryResponse,
    CheckpointSnapshotItem,
    ReplayRequest
)
from ..service import ClaimsService

router = APIRouter(prefix="/threads", tags=["State Snapshots & Time-Travel"])

@router.get("/{thread_id}/state", response_model=ThreadStateResponse)
def get_thread_state(thread_id: str):
    service = ClaimsService.get_instance()
    state = service.get_thread_state(thread_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found or has no state.")
    return ThreadStateResponse(**state)

@router.get("/{thread_id}/history", response_model=ThreadHistoryResponse)
def get_thread_history(thread_id: str):
    service = ClaimsService.get_instance()
    checkpoints = service.get_thread_history(thread_id)
    if not checkpoints:
        raise HTTPException(status_code=404, detail=f"No checkpoint history found for thread '{thread_id}'.")
    return ThreadHistoryResponse(
        thread_id=thread_id,
        total_checkpoints=len(checkpoints),
        checkpoints=[CheckpointSnapshotItem(**cp) for cp in checkpoints]
    )
