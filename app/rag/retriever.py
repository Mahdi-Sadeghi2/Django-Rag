"""Semantic retrieval over the chunk embeddings stored in pgvector.

This is the heart of the RAG pipeline: embed the user's question with
the SAME model used at indexing time, then find the k nearest chunk
vectors by cosine distance in PostgreSQL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.rag.embedding import embed_texts
from app.storage.database import get_engine

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    """One retrieval result — everything a caller (MCP tool, evaluation,
    future LLM) needs to build an answer with a proper source citation."""
    page_url: str
    page_title: str
    heading_path: str
    content: str
    chunk_index: int
    similarity: float   # 0..1 — higher means more relevant


def search(query: str, k: int = 5, engine: Engine | None = None) -> list[SearchHit]:
    """Return the k most semantically relevant chunks for a query.

    Notes on the SQL (each point earned its place the hard way):
    - The query vector is embedded with the same model as the corpus —
      query and documents must share one vector space to be comparable.
    - The vector is sent as a '[0.1,0.2,...]' string and CAST to the
      pgvector type in SQL. Two pitfalls avoided here:
        * psycopg2 sends a plain Python list as numeric[], and
          'vector <=> numeric[]' raises "operator does not exist";
        * the '::vector' cast syntax collides with SQLAlchemy's
          ':name' bind-parameter parser, so CAST(... AS ...) is used.
    - <=> is pgvector's cosine *distance* (0 = identical). We convert
      to a more intuitive similarity score: similarity = 1 - distance,
      so higher = more relevant.
    - The ORDER BY on the <=> expression is what lets PostgreSQL use
      the HNSW index automatically — no index hint needed.
    - A LIMIT of k, larger than the cap enforced by the MCP layer,
      is the caller's responsibility; search itself trusts its input.

    Args:
        query: natural-language question or topic.
        k: number of results to return.
        engine: optional injected engine (tests); defaults to the
            shared read-write engine — the MCP server passes its own
            read-only engine.

    Returns:
        List of SearchHit, most relevant first (possibly empty).
    """
    engine = engine or get_engine()

    # 1) Embed the query (uses the cached model — fast after first call).
    query_vec = embed_texts([query])[0]
    # 2) Serialize to pgvector's string format; 6 decimal places are
    #    far beyond any meaningful similarity precision and keep the
    #    payload small.
    query_vec_str = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"

    sql = text("""
        SELECT page_url, page_title, heading_path, content, chunk_index,
               1 - (embedding <=> CAST(:qv AS vector)) AS similarity
        FROM chunks
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :k
    """)

    with engine.connect() as conn:  # read-only intent — no transaction needed
        rows = conn.execute(sql, {"qv": query_vec_str, "k": k}).all()

    hits = [
        SearchHit(
            page_url=r[0], page_title=r[1], heading_path=r[2],
            content=r[3], chunk_index=r[4], similarity=float(r[5]),
        )
        for r in rows
    ]
    # Structured log line: makes search behavior observable in the
    # MCP server logs (useful for debugging tool calls from a client).
    logger.info("search(%r, k=%d) → %d hits, top similarity %.3f",
                query, k, len(hits), hits[0].similarity if hits else 0.0)
    return hits
