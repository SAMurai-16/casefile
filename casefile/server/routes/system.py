import os
from fastapi import APIRouter
from ..schemas import SystemHealthResponse, SystemConfigResponse
from ..service import ClaimsService
from ...config import (
    DEFAULT_PROVIDER,
    DEFAULT_MODEL,
    MAX_STEPS,
    COST_CEILING_USD,
    MAX_REWORK_COUNT
)
from ..config import CHECKPOINT_DB_PATH

router = APIRouter(prefix="/system", tags=["System & Health"])

@router.get("/health", response_model=SystemHealthResponse)
def get_health():
    service = ClaimsService.get_instance()
    db_ok = CHECKPOINT_DB_PATH.exists()
    return SystemHealthResponse(
        status="ok",
        version="0.1.0",
        checkpointer_status="active",
        database_status="connected" if db_ok else "in_memory"
    )

@router.get("/config", response_model=SystemConfigResponse)
def get_config():
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    return SystemConfigResponse(
        llm_provider=provider,
        llm_model=model,
        max_steps_guard=MAX_STEPS,
        cost_ceiling_guard_usd=COST_CEILING_USD,
        checkpointer_backend="sqlite" if CHECKPOINT_DB_PATH.exists() else "memory",
        default_rework_limit=MAX_REWORK_COUNT
    )
