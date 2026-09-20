#!/usr/bin/env python3
from __future__ import annotations
from app.config import settings
from app.crawler.extractor import ContentExtractor
from app.crawler.fetcher import PageFetcher
from app.storage.database import init_db
from app.storage.repository import PageRepository
import logging
import sys
from pathlib import Path


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
    logger.debug("DB target: %s:%s/%s",
                 settings.postgres_host,
                 settings.postgres_port,
                 settings.postgres_db)
    init_db()
    repo = PageRepository()
    fetcher = PageFetcher()
    extractor = ContentExtractor()

    links = fetcher.discover_topic_links()
    if not links:
        logger.error("No topic links discovered. Aborting.")
        sys.exit(1)

    links = links[: settings.max_pages]
    logger.info("Will process %d pages", len(links))

    success = failed = 0

    for i, url in enumerate(links, start=1):
        logger.info("[%d/%d] Processing %s", i, len(links), url)

        html = fetcher.fetch(url)
        if html is None:
            failed += 1
            continue

        page = extractor.extract(html, url)
        if page is None:
            failed += 1
            continue

        if repo.upsert(page):
            success += 1
            logger.info("  → Saved: %s (%d chars)",
                        page.title, len(page.content))
        else:
            failed += 1

    logger.info("=" * 50)
    logger.info("Finished. Success: %d | Failed: %d | Total in DB: %d",
                success, failed, repo.count())


if __name__ == "__main__":
    main()
