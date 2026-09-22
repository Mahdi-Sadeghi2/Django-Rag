
"""Crawl the Django documentation Topics section and store clean pages.

Pipeline per page: fetch (cache-aware) -> extract -> upsert.
Idempotent: re-running is safe — unchanged pages are skipped by the
content_hash check in the repository, and cached pages cost zero
network requests. A single failing page never aborts the run.
"""
from __future__ import annotations
from app.config import settings
from app.crawler.extractor import ContentExtractor
from app.crawler.fetcher import PageFetcher
from app.storage.database import init_db
from app.storage.repository import PageRepository
import logging
import sys
from pathlib import Path


# Make the project root importable when running as a plain script
# (`python scripts/crawl.py` puts scripts/, not the root, on sys.path).
# Must run BEFORE any `app.` import — see LEARNING.md, this ordering
# once broke silently when the editor reordered imports.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crawl")


def main() -> None:
    logger.info("Starting crawl of Django Topics")
    # DB target WITHOUT credentials (host/port/name only) — the full
    # database_url contains the password and must never be logged.
    logger.debug("DB target: %s:%s/%s",
                 settings.postgres_host,
                 settings.postgres_port,
                 settings.postgres_db)
    # Creates tables if missing; no-op when they exist (idempotent).
    init_db()
    repo = PageRepository()
    fetcher = PageFetcher()
    extractor = ContentExtractor()

    # Step 1: discover which topic pages exist.
    links = fetcher.discover_topic_links()
    if not links:
        logger.error("No topic links discovered. Aborting.")
        sys.exit(1)

    # Respect the task's page budget (40-80 pages suggested).
    links = links[: settings.max_pages]
    logger.info("Will process %d pages", len(links))

    success = failed = 0

    # Step 2: fetch -> extract -> store, one page at a time.
    # Every failure path just increments `failed` and continues —
    # one bad page must not kill the whole crawl (task requirement).
    for i, url in enumerate(links, start=1):
        logger.info("[%d/%d] Processing %s", i, len(links), url)

        # Network failure (or a cached copy is absent and download
        # failed) — skip this page, keep going.
        html = fetcher.fetch(url)
        if html is None:
            failed += 1
            continue

        # Extraction failure, or the page was filtered as an empty
        # index/landing page (content < MIN_CONTENT_CHARS).
        page = extractor.extract(html, url)
        if page is None:
            failed += 1
            continue

        # Upsert: insert new page or update only if content changed
        # (content_hash comparison inside the SQL). Returns False on
        # DB errors — logged inside the repository.
        if repo.upsert(page):
            success += 1
            logger.info("  → Saved: %s (%d chars)",
                        page.title, len(page.content))
        else:
            failed += 1

    # Final summary — quick sanity check after every run.
    logger.info("=" * 50)
    logger.info("Finished. Success: %d | Failed: %d | Total in DB: %d",
                success, failed, repo.count())


if __name__ == "__main__":
    main()
