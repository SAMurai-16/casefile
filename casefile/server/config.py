import os
from pathlib import Path
from ..config import BASE_DIR, CHECKPOINT_DIR

SERVER_HOST: str = os.getenv("CASEFILE_SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("CASEFILE_SERVER_PORT", "8000"))
CORS_ORIGINS: list = [
    origin.strip()
    for origin in os.getenv("CASEFILE_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

# Ensure checkpoint dir exists
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_DB_PATH: Path = CHECKPOINT_DIR / "checkpoints.sqlite"
