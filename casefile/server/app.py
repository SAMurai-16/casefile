from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS, CHECKPOINT_DB_PATH
from .routes.system import router as system_router
from .routes.claims import router as claims_router
from .routes.human_gate import router as human_gate_router
from .routes.snapshots import router as snapshots_router
from .routes.traces import router as traces_router
from .service import ClaimsService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure ClaimsService singleton is initialized
    service = ClaimsService.get_instance()
    print("=" * 70)
    print("🚀 CaseFile Agentic Claims API starting up...")
    print(f"📦 Checkpoint Database: {CHECKPOINT_DB_PATH}")
    print(f"⚡ Available Claims: {len(service.list_claims())}")
    print("=" * 70)
    yield
    print("🛑 CaseFile Agentic Claims API shutting down...")

def create_app() -> FastAPI:
    app = FastAPI(
        title="CaseFile Multi-Agent Claims Orchestration API",
        description=(
            "Production-grade Multi-Agent Claims Adjudication system featuring LangGraph state machines, "
            "Server-Sent Events (SSE) live streaming, Human-in-the-Loop (HITL) approval gates, and "
            "checkpoint time-travel replay."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root informational endpoint
    @app.get("/", tags=["Root"])
    def root():
        return {
            "name": "CaseFile Multi-Agent Claims API",
            "version": "0.1.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "endpoints": {
                "claims": "/api/v1/claims",
                "approval_gate": "/api/v1/approval-gate",
                "threads": "/api/v1/threads",
                "analytics": "/api/v1/analytics/summary",
                "system": "/api/v1/system/health"
            }
        }

    # Mount API v1 Routers
    api_v1_prefix = "/api/v1"
    app.include_router(system_router, prefix=api_v1_prefix)
    app.include_router(claims_router, prefix=api_v1_prefix)
    app.include_router(human_gate_router, prefix=api_v1_prefix)
    app.include_router(snapshots_router, prefix=api_v1_prefix)
    app.include_router(traces_router, prefix=api_v1_prefix)

    return app

app = create_app()
