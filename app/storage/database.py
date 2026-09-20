from __future__ import annotations
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from app.config import settings

logger = logging.getLogger(__name__)


def get_engine() -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)


def init_db(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chunks (
                id           SERIAL PRIMARY KEY,
                page_url     TEXT NOT NULL REFERENCES pages(url) ON DELETE CASCADE,
                page_title   TEXT NOT NULL,
                content      TEXT NOT NULL,
                heading_path TEXT NOT NULL DEFAULT '',
                chunk_index  INT  NOT NULL,
                token_count  INT,
                embedding    vector(384),
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (page_url, chunk_index)
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding
            ON chunks USING hnsw (embedding vector_cosine_ops)
        """))


logger.info("Database schema is ready")
