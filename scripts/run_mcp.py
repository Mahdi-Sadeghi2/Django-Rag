
from __future__ import annotations
from app.mcp_server.server import run
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


if __name__ == "__main__":
    run()
