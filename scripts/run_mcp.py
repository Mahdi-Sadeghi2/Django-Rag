
"""Launch the MCP server (stdio transport).

This is the entry point that MCP clients run, e.g.:

    npx @modelcontextprotocol/inspector python scripts/run_mcp.py

The client communicates with the server over stdin/stdout; the server
in turn talks to PostgreSQL with the read-only user. The project root
is added to sys.path because the client's working directory is not
necessarily the project root.
"""
# isort: skip_file
from __future__ import annotations
from app.mcp_server.server import run
import sys
from pathlib import Path

# Must run BEFORE the `app.` import above (same ordering rule as the
# other scripts — see LEARNING.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


if __name__ == "__main__":
    run()
