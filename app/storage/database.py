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
    logger.info("Database schema is ready")
