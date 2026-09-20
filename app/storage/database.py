from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

logger = logging.getLogger(__name__)


def get_engine() -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)


def init_db(engine: Engine | None = None) -> None:
    """جداول و افزونه‌ها را ایجاد می‌کند — idempotent (قابل اجرای مکرر)."""
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pages (
                id              SERIAL PRIMARY KEY,
                url             TEXT NOT NULL UNIQUE,
                title           TEXT NOT NULL,
                content         TEXT NOT NULL,
                headings        JSONB NOT NULL DEFAULT '[]',
                content_hash    TEXT NOT NULL,
                scraped_at      TIMESTAMPTZ NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pages_content_hash
            ON pages (content_hash)
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chunks (
                id           SERIAL PRIMARY KEY,
                page_url     TEXT NOT NULL REFERENCES pages(url) ON DELETE CASCADE,
                page_title   TEXT NOT NULL,
                content      TEXT NOT NULL,
                heading_path TEXT NOT NULL DEFAULT '',
                chunk_index  INT  NOT NULL,
                token_count  INT,
                embedding    vector(384) NOT NULL,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (page_url, chunk_index)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding
            ON chunks USING hnsw (embedding vector_cosine_ops)
        """))

    logger.info("Database schema is ready")
