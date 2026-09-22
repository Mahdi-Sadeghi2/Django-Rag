"""Database schema and connection management.

Defines the two engines used by the project:
- get_engine():          main read-write connection (crawler, indexer)
- get_readonly_engine(): SELECT-only connection dedicated to the MCP server

And init_db(): an idempotent schema bootstrap (safe to run repeatedly).
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

logger = logging.getLogger(__name__)


def get_engine() -> Engine:
    """Create the main read-write engine (used by crawler and indexer).

    pool_pre_ping=True: SQLAlchemy sends a lightweight check before
    handing out a pooled connection, so a connection that died (e.g.
    the Docker container restarted between runs) is silently replaced
    instead of raising 'connection refused' mid-run.
    """
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_readonly_engine() -> Engine:
    """Read-only engine for the MCP server.

    Connects with the dedicated `rag_readonly` user, which has SELECT
    rights only. This is a defense-in-depth security layer (task
    requirement): even if tool input were malicious or a query were
    buggy, the connection physically cannot INSERT/UPDATE/DELETE.

    pool_size=2: the MCP server handles one request at a time, so a
    small pool is enough and keeps idle connections minimal.
    """
    url = (
        f"postgresql://{settings.mcp_db_user}:{settings.mcp_db_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    return create_engine(url, pool_pre_ping=True, pool_size=2)


def init_db(engine: Engine | None = None) -> None:
    """Create extensions, tables and indexes — idempotent.

    Everything uses IF NOT EXISTS, so calling this on every script
    start is cheap and safe. The `engine` parameter allows tests to
    inject a different (e.g. temporary) database.
    """
    engine = engine or get_engine()
    with engine.begin() as conn:  # begin() = one transaction: all-or-nothing
        # pgvector: enables the `vector` column type and the cosine
        # distance operator (<=>) used by the retriever.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # --- pages: one row per crawled documentation page ---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pages (
                id              SERIAL PRIMARY KEY,
                url             TEXT NOT NULL UNIQUE,   -- natural key; upsert target
                title           TEXT NOT NULL,
                content         TEXT NOT NULL,          -- cleaned main text
                headings        JSONB NOT NULL DEFAULT '[]',  -- h1-h3 outline
                content_hash    TEXT NOT NULL,          -- sha256 of content;
                                -- used by the upsert to skip unchanged pages
                scraped_at      TIMESTAMPTZ NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        # Supports the "is this page changed?" lookup pattern.
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pages_content_hash
            ON pages (content_hash)
        """))

        # --- chunks: text pieces cut from pages, with embeddings ---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chunks (
                id           SERIAL PRIMARY KEY,
                page_url     TEXT NOT NULL REFERENCES pages(url) ON DELETE CASCADE,
                             -- CASCADE: deleting a page automatically removes
                             -- its chunks — no orphan rows left behind
                page_title   TEXT NOT NULL,
                content      TEXT NOT NULL,
                heading_path TEXT NOT NULL DEFAULT '',  -- e.g. 'Sessions > Security'
                             -- adds semantic context to the embedding and
                             -- makes results self-describing for the caller
                chunk_index  INT  NOT NULL,             -- position within the page
                token_count  INT,
                embedding    vector(384) NOT NULL,      -- 384 = all-MiniLM-L6-v2 dim
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (page_url, chunk_index)          -- no duplicate chunks on re-index
            )
        """))
        # HNSW approximate-nearest-neighbor index on the embedding.
        # For ~1400 chunks a full scan would also be fast, but the index
        # is the correct pattern for growth and does not hurt here.
        # vector_cosine_ops matches the <=> operator used in search.
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding
            ON chunks USING hnsw (embedding vector_cosine_ops)
        """))

    logger.info("Database schema is ready")
