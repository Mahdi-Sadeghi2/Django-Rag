from __future__ import annotations
from app.storage.database import get_engine
from app.rag.chunking import chunk_section, split_by_headings

from sqlalchemy import text
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("index")


def main() -> None:
    engine = get_engine()

    # آمار chunking قبل از ذخیره — برای ارزیابی تصمیم‌ها
    total_chunks = 0
    oversized = 0

    with engine.connect() as conn:
        pages = conn.execute(
            text("SELECT url, title, content FROM pages")).all()

    for url, title, content in pages:
        for heading_path, section in split_by_headings(content):
            pieces = chunk_section(section)
            for i, piece in enumerate(pieces):
                total_chunks += 1
                if len(piece) > 1200:
                    oversized += 1

    logger.info("Total chunks: %d | oversized: %d", total_chunks, oversized)
    logger.info("Avg per page: %.1f", total_chunks / max(len(pages), 1))


if __name__ == "__main__":
    main()
