#!/usr/bin/env python3
# isort: skip_file
from __future__ import annotations
from app.storage.database import get_engine, init_db
from app.rag.embedding import embed_texts
from app.rag.chunking import chunk_section, split_by_headings
from sqlalchemy import text
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("index")


MIN_CHUNK_CHARS = 50

# تنظیم‌پذیر از محیط — برای مقایسه‌ی تنظیمات chunking در ارزیابی
MAX_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "1200"))
OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "150"))


def main() -> None:
    init_db()
    engine = get_engine()

    with engine.connect() as conn:
        pages = conn.execute(
            text("SELECT url, title, content FROM pages")).all()

    logger.info("Chunking config: max_chars=%d overlap=%d", MAX_CHARS, OVERLAP)
    logger.info("Indexing %d pages ...", len(pages))
    total = skipped = 0

    for url, title, content in pages:
        pieces: list[tuple[str, str]] = []  # (heading_path, text)

        for heading_path, section in split_by_headings(content):
            for piece in chunk_section(section, max_chars=MAX_CHARS,
                                       overlap_chars=OVERLAP):
                if len(piece) < MIN_CHUNK_CHARS:
                    skipped += 1
                    continue
                # سرفصل را به ابتدای متن می‌چسبانیم تا مدل امبدینگ زمینه داشته باشد
                embed_input = (f"{title}\n{heading_path}\n{piece}"
                               if heading_path else f"{title}\n{piece}")
                pieces.append((heading_path, piece, embed_input))

        if not pieces:
            continue

        vectors = embed_texts([p[2] for p in pieces])

        # delete + insert در یک تراکنش = idempotent؛ چانک‌های کهنه‌ی صفحه‌ی
        # تغییرکرده (وقتی تعداد چانک کم شده) یتیم نمی‌مانند
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM chunks WHERE page_url = :url"), {"url": url})
            for i, ((hp, piece, _), vec) in enumerate(zip(pieces, vectors)):
                conn.execute(text("""
                    INSERT INTO chunks (page_url, page_title, content,
                                        heading_path, chunk_index, token_count, embedding)
                    VALUES (:url, :title, :content, :hp, :i, :tc, :emb)
                """), {
                    "url": url, "title": title, "content": piece,
                    "hp": hp, "i": i, "tc": len(piece) // 4, "emb": vec.tolist(),
                })
        total += len(pieces)

    logger.info("Done. Indexed chunks: %d | skipped tiny: %d", total, skipped)


if __name__ == "__main__":
    main()
