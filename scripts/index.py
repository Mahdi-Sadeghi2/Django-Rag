
"""Chunk all stored pages, embed the chunks and index them in pgvector.

Pipeline: pages -> split_by_headings -> chunk_section -> embed ->
DELETE+INSERT into chunks. Rerunnable: each page's chunks are fully
replaced in one transaction, so the table always reflects the last
indexing run with the current chunking config.

Chunking parameters can be overridden via environment variables
(CHUNK_MAX_CHARS, CHUNK_OVERLAP) — this is how the three evaluation
configs (A/B/C in results.md) were produced without code changes.
"""
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

# Project root on sys.path — must run BEFORE the `app.` imports above
# (kept deliberately at this position; see LEARNING.md for the lesson
# about import reorderers silently breaking this).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("index")


# Chunks shorter than this carry too little meaning to be useful
# retrieval units (a bare fragment or lone title) — drop them.
MIN_CHUNK_CHARS = 50

# Configurable via env — used for comparing chunking settings in the
# evaluation (A: 1200/150, B: 1200/0, C: 600/0 — see results.md).
MAX_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "1200"))
OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "150"))


def main() -> None:
    # Idempotent bootstrap: also creates the chunks table if missing.
    init_db()
    engine = get_engine()

    with engine.connect() as conn:
        pages = conn.execute(
            text("SELECT url, title, content FROM pages")).all()

    # Log the active config — makes every index run self-documenting
    # in the logs (this is how we caught that an env var hadn't applied).
    logger.info("Chunking config: max_chars=%d overlap=%d", MAX_CHARS, OVERLAP)
    logger.info("Indexing %d pages ...", len(pages))
    total = skipped = 0

    for url, title, content in pages:
        pieces: list[tuple[str, str]] = []  # (heading_path, text, embed_input)

        for heading_path, section in split_by_headings(content):
            for piece in chunk_section(section, max_chars=MAX_CHARS,
                                       overlap_chars=OVERLAP):
                # Discard fragments too small to be meaningful retrieval units.
                if len(piece) < MIN_CHUNK_CHARS:
                    skipped += 1
                    continue
                # Prepend title + heading path to the text BEFORE embedding:
                # a bare chunk like "Django provides a way to..." lacks
                # context for the embedding model; "Sessions > Clearing
                # sessions" tells it what the passage is about. This is
                # the cheapest quality boost in the whole pipeline.
                embed_input = (f"{title}\n{heading_path}\n{piece}"
                               if heading_path else f"{title}\n{piece}")
                pieces.append((heading_path, piece, embed_input))

        if not pieces:
            continue

        # Batch-embed all pieces of this page in one model call.
        vectors = embed_texts([p[2] for p in pieces])

        # DELETE + INSERT inside ONE transaction = idempotent re-indexing.
        # (Upinsert alone would leave orphaned chunks if a page now
        # produces fewer chunks than before.) On any error the whole
        # page rolls back to its previous consistent state.
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
                    # tc: rough token estimate (chars/4) — good enough
                    # for budgeting context windows later.
                })
        total += len(pieces)

    logger.info("Done. Indexed chunks: %d | skipped tiny: %d", total, skipped)


if __name__ == "__main__":
    main()
