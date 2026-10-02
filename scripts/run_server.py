import argparse
import sys
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from casefile.server.config import SERVER_HOST, SERVER_PORT

def main():
    parser = argparse.ArgumentParser(description="Run the CaseFile Multi-Agent API Server.")
    parser.add_argument("--host", default=SERVER_HOST, help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    print(f"Starting CaseFile API Server on http://{args.host}:{args.port}")
    print(f"Swagger Documentation available at: http://localhost:{args.port}/docs")

    uvicorn.run(
        "casefile.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level="info"
    )

if __name__ == "__main__":
    main()
