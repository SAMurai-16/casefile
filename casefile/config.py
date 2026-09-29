import os
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root and current working directory
load_dotenv(BASE_DIR / ".env")
load_dotenv()
DATA_DIR = Path(os.getenv("CASEFILE_DATA_DIR", BASE_DIR / "data" / "claims"))
CHECKPOINT_DIR = Path(os.getenv("CASEFILE_CHECKPOINT_DIR", BASE_DIR / ".checkpoints"))
TRACES_DIR = Path(os.getenv("CASEFILE_TRACES_DIR", BASE_DIR / "traces"))

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
TRACES_DIR.mkdir(parents=True, exist_ok=True)

# Guard Rails & Ceilings
MAX_STEPS: int = int(os.getenv("MAX_STEPS", "15"))
MAX_REWORK_COUNT: int = int(os.getenv("MAX_REWORK_COUNT", "2"))
TOKEN_CEILING: int = int(os.getenv("TOKEN_CEILING", "50000"))
COST_CEILING_USD: float = float(os.getenv("COST_CEILING_USD", "2.00"))

# Provider Configuration
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # "gemini", "openai", "mock"
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")

# Model Pricing Table (USD per 1,000,000 tokens)
PRICING_TABLE = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    "mock": {"input": 0.00, "output": 0.00},
}
