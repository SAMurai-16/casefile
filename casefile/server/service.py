import asyncio
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from langgraph.types import Command
from ..config import CHECKPOINT_DIR, BASE_DIR
from ..store import ClaimStore, get_checkpointer
from ..graph import build_claims_graph
from ..schema import ClaimState, HumanDecision, ExtractionResult, InvestigationResult, ReviewResult
from ..tracing import TraceLogger
from .config import CHECKPOINT_DB_PATH
from .schemas import HumanDecisionRequest, ClaimIngestRequest

class ClaimsService:
    """
    Central business logic service for CaseFile FastAPI Backend.
    Manages Graph compilation, SqliteSaver checkpointer, background runs,
    real-time SSE streaming queues, and HITL approval gates.
    """
    _instance: Optional["ClaimsService"] = None

    def __init__(self):
        CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            self._conn = sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
            self.checkpointer = SqliteSaver(self._conn)
            self.checkpointer.setup()
        except Exception as e:
            from langgraph.checkpoint.memory import MemorySaver
            self.checkpointer = MemorySaver()

        self.claim_store = ClaimStore()
        self.graph = build_claims_graph(checkpointer=self.checkpointer)
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.event_queues: Dict[str, List[asyncio.Queue]] = {}

    @classmethod
    def get_instance(cls) -> "ClaimsService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -------------------------------------------------------------------------
    # 1. CLAIMS REPOSITORY
    # -------------------------------------------------------------------------
    def _normalize_claim_num(self, claim_id_input: str) -> str:
        c = claim_id_input.replace("claim_", "").replace("CLM-2026-00", "").replace("CLM-2026-10", "")
        mapping = {
            "00147": "001", "00203": "002", "00251": "003", "00278": "004", "00299": "005",
            "10001": "001", "10002": "002", "10003": "003", "10004": "004", "10005": "005"
        }
        return mapping.get(c, c)

    def load_claim_dict(self, claim_id_input: str) -> Dict[str, Any]:
        num = self._normalize_claim_num(claim_id_input)
        fnol, est, pol, rental, medical, third_party = self.claim_store.load_claim_package(num)
        return {
            "fnol_raw": fnol,
            "estimate_raw": est,
            "policy_raw": pol,
            "rental_raw": rental,
            "medical_raw": medical,
            "third_party_raw": third_party
        }

    def list_claims(self) -> List[Dict[str, Any]]:
        claim_ids = self.claim_store.list_available_claims()
        results = []
        for cid in sorted(claim_ids):
            try:
                pkg = self.load_claim_dict(cid)
                fnol = pkg.get("fnol_raw", {})
                est = pkg.get("estimate_raw", {})
                pol = pkg.get("policy_raw", {})

                attached = ["FNOL", "Repair Estimate", "Policy"]
                if pkg.get("rental_raw"):
                    attached.append("Rental Receipt")
                if pkg.get("medical_raw"):
                    attached.append("Medical Bill")
                if pkg.get("third_party_raw"):
                    attached.append("Third-Party Claim")

                ph = (
                    pol.get("policyholder", {}).get("name") or 
                    fnol.get("insured_contact", {}).get("full_name") or 
                    "Unknown"
                )
                veh_info = est.get("vehicle") or fnol.get("vehicle") or {}
                veh = f"{veh_info.get('year', '')} {veh_info.get('make', '')} {veh_info.get('model', '')}".strip() or "Insured Vehicle"
                
                total = None
                fin = est.get("cost_summary") or est.get("financial_summary") or est.get("totals_breakdown") or {}
                if fin:
                    total = float(fin.get("grand_total") or fin.get("total_amount") or fin.get("gross_total") or 0.0)

                channel = fnol.get("intake_header", {}).get("channel") or "Standard"
                inc_date = fnol.get("loss_details", {}).get("incident_date") or fnol.get("incident_date")

                results.append({
                    "claim_id": cid,
                    "filing_channel": channel,
                    "incident_date": inc_date,
                    "policyholder_name": ph,
                    "vehicle_summary": veh,
                    "total_claimed": total,
                    "attached_documents": attached
                })
            except Exception as e:
                results.append({
                    "claim_id": cid,
                    "filing_channel": "Standard",
                    "attached_documents": ["Error reading claim"]
                })
        return results

    def get_claim_detail(self, claim_id: str) -> Dict[str, Any]:
        pkg = self.load_claim_dict(claim_id)
        return {
            "claim_id": claim_id,
            "raw_documents": {
                "fnol": pkg.get("fnol_raw"),
                "estimate": pkg.get("estimate_raw"),
                "policy": pkg.get("policy_raw"),
                "rental": pkg.get("rental_raw"),
                "medical": pkg.get("medical_raw"),
                "third_party": pkg.get("third_party_raw"),
            }
        }

    def ingest_claim(self, req: ClaimIngestRequest) -> Dict[str, Any]:
        # Determine claim number
        claim_num = req.claim_id
        if not claim_num:
            claim_num = (
                req.fnol_raw.get("claim_id") or 
                req.fnol_raw.get("intake_header", {}).get("claim_id")
            )
        if not claim_num:
            existing = self.claim_store.list_available_claims()
            num_ids = [int(cid) for cid in existing if cid.isdigit()]
            next_num = max(num_ids) + 1 if num_ids else 1
            claim_num = f"{next_num:03d}"

        cleaned_num = claim_num.replace("claim_", "")

        saved_id = self.claim_store.save_claim_package(
            claim_num=cleaned_num,
            fnol_raw=req.fnol_raw,
            estimate_raw=req.estimate_raw,
            policy_raw=req.policy_raw,
            rental_raw=req.rental_raw,
            medical_raw=req.medical_raw,
            third_party_raw=req.third_party_raw
        )

        return {
            "claim_id": saved_id,
            "message": f"Claim '{saved_id}' successfully ingested into claim store."
        }

    # -------------------------------------------------------------------------
    # 2. RUN EXECUTION & STREAMING
    # -------------------------------------------------------------------------
    def register_event_queue(self, run_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        if run_id not in self.event_queues:
            self.event_queues[run_id] = []
        self.event_queues[run_id].append(q)
        return q

    def unregister_event_queue(self, run_id: str, q: asyncio.Queue):
        if run_id in self.event_queues:
            self.event_queues[run_id] = [eq for eq in self.event_queues[run_id] if eq is not q]
            if not self.event_queues[run_id]:
                del self.event_queues[run_id]

    def _emit_event_sync(self, run_id: str, event_type: str, data: Any, loop: Optional[asyncio.AbstractEventLoop] = None):
        if run_id in self.event_queues:
            for q in list(self.event_queues[run_id]):
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, {"event": event_type, "data": data})
                else:
                    try:
                        q.put_nowait({"event": event_type, "data": data})
                    except Exception:
                        pass

    def launch_claim_run(
        self,
        claim_id: str,
        auto_approve: bool = False,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pkg = self.load_claim_dict(claim_id)
        canonical_claim_id = pkg["fnol_raw"].get("claim_id") or claim_id
        run_id = uuid.uuid4().hex[:8]
        th_id = thread_id or f"thread_{canonical_claim_id}_{run_id}"

        initial_state: ClaimState = {
            "claim_id": canonical_claim_id,
            "run_id": run_id,
            "thread_id": th_id,
            "fnol_raw": pkg["fnol_raw"],
            "estimate_raw": pkg["estimate_raw"],
            "policy_raw": pkg["policy_raw"],
            "rental_raw": pkg.get("rental_raw"),
            "medical_raw": pkg.get("medical_raw"),
            "third_party_raw": pkg.get("third_party_raw"),
            "extraction": None,
            "investigation": None,
            "review": None,
            "human_decision": None,
            "current_phase": "intake",
            "active_worker": None,
            "rework_count": 0,
            "rework_target": None,
            "rework_instructions": None,
            "step_count": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "handoff_history": [],
            "payout_breakdown": {},
            "final_payout_amount": 0.0,
            "terminal_status": None,
            "settlement_summary": None
        }

        self.runs[run_id] = {
            "run_id": run_id,
            "thread_id": th_id,
            "claim_id": canonical_claim_id,
            "status": "running",
            "current_phase": "intake",
            "active_node": None,
            "step_count": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "is_paused_at_gate": False,
            "terminal_status": None,
            "final_payout_amount": None,
            "payout_breakdown": None,
            "settlement_summary": None,
            "auto_approve": auto_approve,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        t = threading.Thread(
            target=self._execute_graph_run,
            args=(run_id, th_id, initial_state, auto_approve, loop),
            daemon=True
        )
        t.start()

        return {
            "claim_id": canonical_claim_id,
            "run_id": run_id,
            "thread_id": th_id,
            "status": "running",
            "message": f"Claim run {run_id} started on thread {th_id}."
        }

    def _execute_graph_run(
        self,
        run_id: str,
        thread_id: str,
        input_data: Any,
        auto_approve: bool,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ):
        config = {"configurable": {"thread_id": thread_id}}
        logger = TraceLogger(claim_id=self.runs[run_id]["claim_id"], run_id=run_id)

        try:
            for event in self.graph.stream(input_data, config=config):
                for node_name, node_update in event.items():
                    if node_name == "__interrupt__" or not isinstance(node_update, dict):
                        continue
                    step = node_update.get("step_count", 0)
                    tokens = node_update.get("total_tokens", 0)
                    cost = node_update.get("total_cost_usd", 0.0)
                    phase = node_update.get("current_phase", "")
                    logger.record_node_entry(node_name, step, tokens, cost)

                    self.runs[run_id].update({
                        "active_node": node_name,
                        "current_phase": phase,
                        "step_count": step,
                        "total_tokens": tokens,
                        "total_cost_usd": cost,
                    })

                    step_payload = {
                        "run_id": run_id,
                        "thread_id": thread_id,
                        "node": node_name,
                        "phase": phase,
                        "step_count": step,
                        "total_tokens": tokens,
                        "total_cost_usd": cost,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    self._emit_event_sync(run_id, "step", step_payload, loop)

            # Check if graph paused at human approval gate
            state_snapshot = self.graph.get_state(config)
            if state_snapshot.next == ("human_gate",) or (state_snapshot.tasks and state_snapshot.tasks[0].interrupts):
                self.runs[run_id]["is_paused_at_gate"] = True
                self.runs[run_id]["status"] = "paused_at_gate"
                
                interrupt_val = {}
                if state_snapshot.tasks and state_snapshot.tasks[0].interrupts:
                    interrupt_val = state_snapshot.tasks[0].interrupts[0].value

                self._emit_event_sync(run_id, "gate_paused", {
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "claim_id": self.runs[run_id]["claim_id"],
                    "dossier": interrupt_val
                }, loop)

                if auto_approve:
                    proposed = interrupt_val.get("total_proposed_payout", 0.0)
                    auto_decision = HumanDecisionRequest(
                        approver_id="senior_adjuster_auto",
                        action="approve",
                        authorized_amount=proposed,
                        comments="Auto-approved via API run configuration."
                    )
                    self.resume_human_decision_sync(thread_id, auto_decision, loop)
                return

            values = state_snapshot.values
            self._finalize_run(run_id, values, logger, loop)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.runs[run_id]["status"] = "error"
            self.runs[run_id]["error"] = str(e)
            self._emit_event_sync(run_id, "error", {"error": str(e)}, loop)

    def _finalize_run(self, run_id: str, values: Dict[str, Any], logger: TraceLogger, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.runs[run_id].update({
            "status": "completed",
            "is_paused_at_gate": False,
            "terminal_status": values.get("terminal_status", "completed"),
            "final_payout_amount": values.get("final_payout_amount", 0.0),
            "payout_breakdown": values.get("payout_breakdown", {}),
            "settlement_summary": values.get("settlement_summary"),
        })
        trace_path = logger.export(values)
        self.runs[run_id]["trace_file"] = str(trace_path)

        self._emit_event_sync(run_id, "completed", {
            "run_id": run_id,
            "terminal_status": values.get("terminal_status"),
            "final_payout_amount": values.get("final_payout_amount"),
            "payout_breakdown": values.get("payout_breakdown"),
            "settlement_summary": values.get("settlement_summary")
        }, loop)
        self._emit_event_sync(run_id, "end", {"message": "Run finished"}, loop)

    # -------------------------------------------------------------------------
    # 3. HUMAN APPROVAL GATE RESUMPTION
    # -------------------------------------------------------------------------
    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        pending = []
        for r_id, r_info in self.runs.items():
            if r_info.get("is_paused_at_gate"):
                th_id = r_info["thread_id"]
                dossier = self.get_approval_dossier(th_id)
                pending.append({
                    "run_id": r_id,
                    "thread_id": th_id,
                    "claim_id": r_info["claim_id"],
                    "created_at": r_info["created_at"],
                    "dossier": dossier
                })
        return pending

    def get_approval_dossier(self, thread_id: str) -> Optional[Dict[str, Any]]:
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = self.graph.get_state(config)
        if not state_snapshot:
            return None

        if state_snapshot.tasks and state_snapshot.tasks[0].interrupts:
            val = state_snapshot.tasks[0].interrupts[0].value
            if isinstance(val, dict):
                res = dict(val)
                res["thread_id"] = thread_id
                return res

        val = state_snapshot.values
        review = val.get("review")
        extraction = val.get("extraction")
        investigation = val.get("investigation")
        proposed = review.proposed_payout_amount if review else 0.0
        breakdown = review.payout_breakdown if review and review.payout_breakdown else {"total": proposed}

        return {
            "claim_id": val.get("claim_id", "Unknown"),
            "thread_id": thread_id,
            "policyholder_vehicle": f"{extraction.vehicle_year} {extraction.vehicle_make} {extraction.vehicle_model}" if extraction else "Vehicle",
            "repair_shop": extraction.repair_facility_name if extraction else "Repair Facility",
            "fraud_risk_score": investigation.fraud_risk_score if investigation else 0,
            "fraud_risk_level": investigation.fraud_risk_level if investigation else "low",
            "siu_referral_recommended": investigation.siu_referral_recommended if investigation else False,
            "detected_fraud_signals": investigation.detected_fraud_signals if investigation else [],
            "actual_cash_value": investigation.actual_cash_value if investigation else 0.0,
            "repair_to_acv_ratio": investigation.repair_to_acv_ratio if investigation else 0.0,
            "is_total_loss_candidate": investigation.is_total_loss_candidate if investigation else False,
            "endorsements_validated": investigation.endorsements_validated if investigation else [],
            "applied_exclusions": investigation.applied_exclusions if investigation else [],
            "clause_audit_notes": investigation.clause_audit_notes if investigation else [],
            "discrepancy_details": review.discrepancy_details if review else [],
            "itemized_payout_breakdown": breakdown,
            "total_proposed_payout": proposed,
            "policy_collision_limit": investigation.collision_limit_per_incident if investigation else 0.0,
            "deductible_applied": investigation.collision_deductible if investigation else 0.0,
            "rental_reimbursement_eligible": investigation.rental_eligible_payout if investigation else 0.0,
            "medical_payments_eligible": investigation.medpay_eligible_payout if investigation else 0.0,
            "liability_warning": review.liability_warning if review else None,
            "recommendation": review.recommendation if review else "approve",
            "justification": review.justification if review else "",
            "action_required": "Please approve, reject, or adjust this multi-line settlement payout."
        }

    def resume_human_decision_sync(
        self,
        thread_id: str,
        decision_req: HumanDecisionRequest,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> Dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        
        target_run_id = None
        for r_id, r_info in self.runs.items():
            if r_info["thread_id"] == thread_id:
                target_run_id = r_id
                break

        curr_state = self.graph.get_state(config)
        review = curr_state.values.get("review")
        proposed = review.proposed_payout_amount if review else 0.0

        human_response = {
            "approver_id": decision_req.approver_id,
            "action": decision_req.action,
            "authorized_amount": decision_req.authorized_amount if decision_req.authorized_amount is not None else proposed,
            "comments": decision_req.comments
        }

        events = []
        for event in self.graph.stream(Command(resume=human_response), config=config):
            events.append(event)

        final_state = self.graph.get_state(config).values
        if target_run_id:
            logger = TraceLogger(claim_id=final_state["claim_id"], run_id=target_run_id)
            self._finalize_run(target_run_id, final_state, logger, loop)

        return {
            "claim_id": final_state.get("claim_id", ""),
            "thread_id": thread_id,
            "action": decision_req.action,
            "final_payout_authorized": final_state.get("final_payout_amount", 0.0),
            "terminal_status": final_state.get("terminal_status", "approved"),
            "settlement_summary": final_state.get("settlement_summary", ""),
            "message": f"Successfully resumed and finalized claim with decision: {decision_req.action.upper()}."
        }

    async def resume_human_decision(
        self,
        thread_id: str,
        decision_req: HumanDecisionRequest
    ) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.resume_human_decision_sync, thread_id, decision_req, loop)

    # -------------------------------------------------------------------------
    # 4. TIME-TRAVEL & SNAPSHOTS
    # -------------------------------------------------------------------------
    def _make_serializable(self, obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        elif isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple, set)):
            return [self._make_serializable(v) for v in obj]
        return obj

    def get_thread_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = self.graph.get_state(config)
        if not snapshot:
            return None
        val = snapshot.values
        return {
            "thread_id": thread_id,
            "claim_id": val.get("claim_id"),
            "current_phase": val.get("current_phase"),
            "next_nodes": list(snapshot.next),
            "is_interrupted": bool(snapshot.tasks and snapshot.tasks[0].interrupts),
            "step_count": val.get("step_count", 0),
            "total_tokens": val.get("total_tokens", 0),
            "total_cost_usd": val.get("total_cost_usd", 0.0),
            "values": self._make_serializable(val)
        }

    def get_run_state(self, run_id: str) -> Optional[Dict[str, Any]]:
        run = self.runs.get(run_id)
        if not run:
            return None
        thread_id = run.get("thread_id")
        if not thread_id:
            return None
        return self.get_thread_state(thread_id)

    def get_thread_history(self, thread_id: str) -> List[Dict[str, Any]]:
        config = {"configurable": {"thread_id": thread_id}}
        history = list(self.graph.get_state_history(config))
        checkpoints = []
        for s in history:
            val = s.values
            step = val.get("step_count", 0)
            phase = val.get("current_phase", "unknown")
            node = val.get("active_worker") or "supervisor"
            cid = s.config.get("configurable", {}).get("checkpoint_id", "")
            ts = s.created_at or datetime.now(timezone.utc).isoformat()
            checkpoints.append({
                "checkpoint_id": cid,
                "step": step,
                "node": node,
                "phase": phase,
                "timestamp": str(ts)
            })
        return checkpoints
