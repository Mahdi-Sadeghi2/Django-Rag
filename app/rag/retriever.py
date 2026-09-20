from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.rag.embedding import embed_texts
from app.storage.database import get_engine

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    """یک نتیجه‌ی بازیابی — همه‌چیزی که مدل زبانی برای پاسخ و ارجاع لازم دارد."""
    page_url: str
    page_title: str
    heading_path: str
    content: str
    chunk_index: int
    similarity: float   # بین 0 و 1 — هرچه بیشتر، مرتبط‌تر


def search(query: str, k: int = 5, engine: Engine | None = None) -> list[SearchHit]:
    """k تکه‌ی مرتبط‌ترین چانک با پرسش را با جست‌وجوی معنایی برمی‌گرداند.

    - بردار پرسش با همان مدلِ ایندکس ساخته می‌شود (هم‌فضایی ضروری است)
    - بردار به‌صورت رشته ارسال و با CAST به نوع pgvector تبدیل می‌شود
      (::vector با placeholder-style پارامترهای SQLAlchemy سازگار نیست)
    - عملگر <=> فاصله‌ی cosine است؛ شباهت = 1 - فاصله
    - ایندکس HNSW به‌صورت خودکار برای این ORDER BY استفاده می‌شود
    """
    engine = engine or get_engine()

    query_vec = embed_texts([query])[0]
    query_vec_str = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"

    sql = text("""
        SELECT page_url, page_title, heading_path, content, chunk_index,
               1 - (embedding <=> CAST(:qv AS vector)) AS similarity
        FROM chunks
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :k
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {"qv": query_vec_str, "k": k}).all()

    hits = [
        SearchHit(
            page_url=r[0], page_title=r[1], heading_path=r[2],
            content=r[3], chunk_index=r[4], similarity=float(r[5]),
        )
        for r in rows
    ]
    logger.info("search(%r, k=%d) → %d hits, top similarity %.3f",
                query, k, len(hits), hits[0].similarity if hits else 0.0)
    return hits
