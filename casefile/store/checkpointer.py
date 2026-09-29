from typing import Literal
from langgraph.checkpoint.memory import MemorySaver

def get_checkpointer(backend: Literal["memory", "sqlite"] = "memory"):
    """
    Returns configured checkpointer.
    Defaults to MemorySaver for fast in-memory execution and testing.
    """
    if backend == "memory":
        return MemorySaver()
    elif backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3
            from ..config import CHECKPOINT_DIR
            db_path = CHECKPOINT_DIR / "checkpoints.sqlite"
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            return SqliteSaver(conn)
        except (ImportError, Exception):
            # Fallback to MemorySaver if sqlite saver has dependency issues
            return MemorySaver()
    return MemorySaver()
