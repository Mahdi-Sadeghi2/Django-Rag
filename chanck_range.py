from __future__ import annotations
from app.storage.database import get_engine
from app.rag.chunking import chunk_section, split_by_headings
from collections import Counter
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

    from collections import Counter

    lengths = []
    for url, title, content in pages:
        for heading_path, section in split_by_headings(content):
            for piece in chunk_section(section):
                lengths.append(len(piece))

        lengths.sort()
        n = len(lengths)
        buckets = Counter()
        for L in lengths:
            if L < 200:
                buckets["<200"] += 1
            elif L < 500:
                buckets["200-500"] += 1
            elif L < 800:
                buckets["500-800"] += 1
            elif L < 1200:
                buckets["800-1200"] += 1
            else:
                buckets[">1200"] += 1

        print("min:", lengths[0], "| median:",
              lengths[n//2], "| max:", lengths[-1])
        for k in ["<200", "200-500", "500-800", "800-1200", ">1200"]:
            print(f"{k:>10}: {buckets.get(k, 0):>5} ({buckets.get(k, 0)*100//n}%)")

        logger.info("Total chunks: %d | oversized: %d",
                    total_chunks, oversized)
        logger.info("Avg per page: %.1f", total_chunks / max(len(pages), 1))


if __name__ == "__main__":
    main()
