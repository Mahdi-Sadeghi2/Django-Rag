"""MCP server exposing semantic search over the Django documentation.

Provides three tools to any MCP client (Claude Desktop, MCP Inspector, ...):
- search_docs: semantic search — when the user asks how something works
  in Django and relevant passages are needed
- get_page: full text of one page — when the URL or exact title is known
- answer: a cited answer assembled from retrieved chunks — direct user question

Tool descriptions (docstrings below) are written FOR the client's
language model: they are what the model reads to decide which tool to
call and with what arguments — write them like documentation for a
colleague, not variable names.
"""
from __future__ import annotations
from app.storage.database import get_readonly_engine
from app.rag.retriever import search as semantic_search
from app.config import settings
from mcp.server.mcpserver import MCPServer

import logging
import sys
from pathlib import Path

# Make the project root importable when this file is launched as a
# script by an MCP client (the client's CWD is not necessarily the
# project root, so sys.path needs the root explicitly).
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# One server instance; the name is what clients display to the user.
mcp = MCPServer("django-docs-rag")

_engine = None


def engine():
    """Lazily create the read-only database engine.

    Lazy (not module-level) so that importing this module for tests or
    introspection does not require a database to be reachable. The
    engine uses the SELECT-only `rag_readonly` user — the first of the
    three security layers documented in the README.
    """
    global _engine
    if _engine is None:
        _engine = get_readonly_engine()
    return _engine


def _clip(text: str, limit: int) -> str:
    """Truncate text to `limit` characters with an explicit marker.

    Security requirement: a 67k-char page must never be shipped to the
    client in full — the cap protects the client's context window and
    the marker makes truncation visible instead of silent.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… [truncated]"


# ---------- Tool 1: search_docs ----------

@mcp.tool()
def search_docs(query: str, k: int = 5) -> str:
    """Semantic search over the official Django documentation (topics
    section). Use when the user asks how something works in Django or
    wants relevant documentation passages. Returns up to k chunks with
    page title, section heading path, URL and a similarity score (0..1).

    Args:
        query: Natural-language question or topic, e.g. 'how middleware works'.
        k: Number of results (1..10, default 5).
    """
    # Input validation: clear message instead of a raw exception
    # (task requirement — tool errors must be readable by the model).
    if not query or not query.strip():
        return "Error: 'query' must be a non-empty string."

    try:
        k = int(k)
    except (TypeError, ValueError):
        return "Error: 'k' must be an integer."
    # Security cap: the client can never pull more than mcp_max_k
    # results regardless of what it asks for.
    k = max(1, min(k, settings.mcp_max_k))

    hits = semantic_search(query.strip(), k=k, engine=engine())
    if not hits:
        return ("No results found. The documentation index may be empty "
                "or the query may be outside the indexed topics section.")

    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"{i}. [{h.similarity:.3f}] {h.page_title} — {h.heading_path}\n"
            f"   URL: {h.page_url}\n"
            f"   {_clip(h.content, settings.mcp_max_content_chars)}"
        )
    return f"Top {len(hits)} results for: {query!r}\n\n" + "\n\n".join(lines)


# ---------- Tool 2: get_page ----------

@mcp.tool()
def get_page(url_or_id: str) -> str:
    """Return the full cleaned text of one documentation page by URL or
    exact page title. Use when you already know which page you need.

    Args:
        url_or_id: Page URL or exact page title, e.g. 'Middleware'.
    """
    if not url_or_id or not url_or_id.strip():
        return "Error: 'url_or_id' must be a non-empty string."

    from sqlalchemy import text

    ident = url_or_id.strip()
    # Match by exact URL OR exact title (titles are unique in our corpus
    # since each docs page has one h1). Bound parameter — injection-safe.
    sql = text("""
        SELECT url, title, content FROM pages
        WHERE url = :ident OR title = :ident
        LIMIT 1
    """)
    with engine().connect() as conn:
        row = conn.execute(sql, {"ident": ident}).first()

    if row is None:
        # Clear, actionable message — not a raw exception (task requirement).
        return (f"Page not found: {ident!r}. Tip: pass the exact page "
                f"title (e.g. 'Middleware') or the full URL as crawled "
                f"from docs.djangoproject.com.")

    url, title, content = row
    return (f"# {title}\n\nURL: {url}\n\n"
            f"{_clip(content, settings.mcp_max_content_chars)}")


# Confidence threshold: below this similarity a result is NOT considered
# relevant. Data-driven value: the lowest successful hit in our
# evaluation scored 0.483, so 0.45 sits just under real successes while
# clearly rejecting off-topic queries (our pizza test scored 0.30).
MIN_CONFIDENCE = 0.45


# ---------- Tool 3: answer ----------

@mcp.tool()
def answer(question: str) -> str:
    """Answer a Django question using retrieved documentation chunks,
    with source citations. Uses semantic retrieval plus extractive
    synthesis (no external LLM). If nothing relevant is found, honestly
    says so.

    Args:
        question: The user's Django question.
    """
    if not question or not question.strip():
        return "Error: 'question' must be a non-empty string."

    hits = semantic_search(question.strip(), k=5, engine=engine())

    # Task requirement: if the retrieved chunks contain no answer, say
    # so honestly instead of presenting a weak match as an answer.
    if not hits or hits[0].similarity < MIN_CONFIDENCE:
        best = f"{hits[0].similarity:.3f}" if hits else "n/a"
        return ("I could not find relevant documentation for this question "
                f"(best similarity: {best}). The indexed corpus covers only "
                "the 'topics' section of the Django documentation, so "
                "reference/guide pages may be missing. Please rephrase the "
                "question or search the Django docs directly.")

    # Extractive answer (no external LLM): assemble the best chunks
    # with citations — every claim is traceable to its source URL.
    parts = ["Answer based on the Django documentation "
             f"(top {len(hits)} passages):\n"]
    for i, h in enumerate(hits, 1):
        parts.append(
            f"\n[{i}] {h.page_title} — {h.heading_path} "
            f"(similarity {h.similarity:.3f})\n"
            f"    {_clip(h.content, 600)}\n"
            f"    Source: {h.page_url}"
        )
    # Make the extractive nature explicit so the caller knows the
    # passages ARE the answer, not an LLM paraphrase of them.
    parts.append("\nNote: this is an extractive answer assembled from the "
                 "passages above. For the full context, follow the source URLs.")
    return "\n".join(parts)


def run() -> None:
    """Run the server on stdio — the standard transport for local MCP
    clients like Claude Desktop and MCP Inspector."""
    mcp.run(transport="stdio")
