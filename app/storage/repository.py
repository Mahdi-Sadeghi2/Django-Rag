from __future__ import annotations
import json
import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.models import Page
from .database import get_engine

logger = logging.getLogger(__name__)


class PageRepository:
    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_engine()

    def upsert(self, page: Page) -> bool:
        headings_json = json.dumps([h.model_dump() for h in page.headings])
        sql = text("""
            INSERT INTO pages (url, title, content, headings, content_hash, scraped_at)
            VALUES (:url, :title, :content, :headings, :content_hash, :scraped_at)
            ON CONFLICT (url) DO UPDATE SET
                title        = EXCLUDED.title,
                content      = EXCLUDED.content,
                headings     = EXCLUDED.headings,
                content_hash = EXCLUDED.content_hash,
                scraped_at   = EXCLUDED.scraped_at
            WHERE pages.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        """)
        try:
            with self.engine.begin() as conn:
                conn.execute(sql, {
                    "url": page.url,
                    "title": page.title,
                    "content": page.content,
                    "headings": headings_json,
                    "content_hash": page.content_hash,
                    "scraped_at": page.scraped_at,
                })
            return True
        except Exception as exc:
            logger.error("Failed to upsert page %s: %s", page.url, exc)
            return False

    def count(self) -> int:
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM pages"))
            return result.scalar_one()
