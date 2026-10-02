from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from ..schemas import (
    ApprovalDossierResponse,
    HumanDecisionRequest,
    HumanDecisionResponse,
)
from ..service import ClaimsService

router = APIRouter(prefix="/approval-gate", tags=["Human Approval Gate (HITL)"])

@router.get("/pending", response_model=List[Dict[str, Any]])
def list_pending_approvals():
    service = ClaimsService.get_instance()
    return service.get_pending_approvals()

@router.get("/{thread_id}", response_model=ApprovalDossierResponse)
def get_approval_dossier(thread_id: str):
    service = ClaimsService.get_instance()
    dossier = service.get_approval_dossier(thread_id)
    if not dossier:
        raise HTTPException(status_code=404, detail=f"No pending approval dossier found for thread '{thread_id}'.")
    return ApprovalDossierResponse(**dossier)

@router.post("/{thread_id}/decision", response_model=HumanDecisionResponse)
async def submit_human_decision(thread_id: str, decision: HumanDecisionRequest):
    service = ClaimsService.get_instance()
    try:
        res = await service.resume_human_decision(thread_id, decision)
        return HumanDecisionResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit decision: {str(e)}")
