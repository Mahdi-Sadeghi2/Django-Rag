"""Persistence layer for crawled pages.

Encapsulates all SQL for the `pages` table so the crawler itself stays
free of database details. All queries use bound parameters (:name) —
never string formatting — to make SQL injection structurally impossible.
"""

from __future__ import annotations
import json
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models import Page
from .database import get_engine

logger = logging.getLogger(__name__)


class PageRepository:
    """Data-access object for the `pages` table."""

    def __init__(self, engine: Engine | None = None):
        # Dependency injection: tests can pass an engine pointed at a
        # throwaway database; production falls back to the shared one.
        self.engine = engine or get_engine()

    def upsert(self, page: Page) -> bool:
        """Insert the page, or update it if the URL already exists.

        Returns True on success, False on any failure — the crawler
        counts failures and keeps going instead of crashing (task
        requirement: one bad page must not abort the whole run).

        The WHERE clause on the conflict branch is the heart of our
        idempotency guarantee: the UPDATE only fires when the freshly
        computed content_hash differs from the stored one. Re-running
        the crawler on unchanged pages therefore performs a no-op
        write — we saw this live when re-indexing touched only the
        28 pages whose content actually changed.
        """
        # Pydantic models -> plain dicts -> JSON string, matching the
        # JSONB column type in the schema.
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
            with self.engine.begin() as conn:  # begin() = auto-commit/rollback
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
            # Log with the URL for debuggability, but swallow the error:
            # the caller (crawl script) treats False as "this page failed"
            # and continues with the next one.
            logger.error("Failed to upsert page %s: %s", page.url, exc)
            return False

    def count(self) -> int:
        """Total number of stored pages — used for the crawl summary log."""
        with self.engine.connect() as conn:  # connect() = read-only intent
            result = conn.execute(text("SELECT COUNT(*) FROM pages"))
            return result.scalar_one()
