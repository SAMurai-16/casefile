import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
from ..config import TRACES_DIR

class TraceLogger:
    """
    Records the exact execution path taken by each claim run,
    including node transitions, state changes, token metrics, and timestamps.
    """
    def __init__(self, claim_id: str, run_id: str):
        self.claim_id = claim_id
        self.run_id = run_id
        self.node_path: List[str] = []
        self.events: List[Dict[str, Any]] = []
        self.start_time = datetime.now(timezone.utc).isoformat()
        
    def record_node_entry(self, node_name: str, step_count: int, tokens_so_far: int, cost_so_far: float):
        self.node_path.append(node_name)
        self.events.append({
            "event": "node_entry",
            "node": node_name,
            "step": step_count,
            "tokens": tokens_so_far,
            "cost_usd": cost_so_far,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def export(self, final_state: Dict[str, Any]) -> Path:
        trace_file = TRACES_DIR / f"{self.claim_id}_{self.run_id}_trace.json"
        payload = {
            "claim_id": self.claim_id,
            "run_id": self.run_id,
            "start_time": self.start_time,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "node_path": self.node_path,
            "total_steps": final_state.get("step_count", 0),
            "rework_count": final_state.get("rework_count", 0),
            "total_tokens": final_state.get("total_tokens", 0),
            "total_cost_usd": final_state.get("total_cost_usd", 0.0),
            "terminal_status": final_state.get("terminal_status"),
            "final_payout_amount": final_state.get("final_payout_amount"),
            "events": self.events,
            "handoff_history": [
                h if isinstance(h, dict) else h.model_dump() 
                for h in final_state.get("handoff_history", [])
            ]
        }
        with open(trace_file, "w") as fp:
            json.dump(payload, fp, indent=2)
        return trace_file
