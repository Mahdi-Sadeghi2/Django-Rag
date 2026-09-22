"""Hybrid retrieval: vector search + keyword search, fused with RRF.

Motivation (from our own evaluation): pure semantic search failed the
'get_absolute_url' question — embeddings understand *meaning* but are
weak on exact identifiers (method/class/setting names), which a simple
SQL ILIKE finds instantly. Fusing the two result lists covers each
method's blind spot.

Fusion method: Reciprocal Rank Fusion (RRF) —
    score(d) = Σ 1 / (RRF_K + rank_i(d))
RRF is used because it needs no score normalization between lists
(similarity 0..1 vs. term-hit counts are incomparable directly) —
only the *ranks* matter. A document appearing in both lists collects
two contributions, which is exactly the signal we want for
identifier-like queries.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.rag.embedding import embed_texts
from app.storage.database import get_engine

logger = logging.getLogger(__name__)

# Standard RRF constant (from the original RRF paper): dampens the
# dominance of top ranks so one list can't completely outshout the other.
RRF_K = 60

# Small English stopword set — enough to keep generic question words
# out of the keyword query; deliberately minimal, not a full NLP list.
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "how", "what", "why", "when", "which", "who", "do", "does",
    "did", "can", "could", "should", "would", "in", "on", "at",
    "to", "for", "of", "with", "and", "or", "not", "it", "its",
    "this", "that", "these", "those", "i", "you", "we", "they",
    "used", "use", "using", "work", "works", "working",
}


@dataclass
class HybridHit:
    """One fused result. `matched_by` records which search lists
    produced it — kept for evaluation analysis (did fusion actually
    combine evidence, or did one list win?)."""
    page_url: str
    page_title: str
    heading_path: str
    content: str
    similarity: float          # vector similarity (0.0 if keyword-only hit)
    rrf_score: float           # fused ranking score (higher = better)
    matched_by: str            # 'vector', 'keyword', or 'both'


def _keyword_terms(query: str) -> list[str]:
    """Extract keyword-search terms from a natural-language question.

    Keeps words that are likely identifiers or domain terms:
    - longer than 3 chars (drops 'how', 'is', ...)
    - not in the stopword set
    - snake_case / CamelCase tokens are preserved intact because they
      are usually exact identifiers (get_absolute_url, SessionMiddleware)
      — lowercasing them would still match ILIKE (case-insensitive),
      but preserving the original form keeps logs readable.
    """
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
    terms = []
    for w in words:
        lw = w.lower()
        if len(lw) <= 3 or lw in STOPWORDS:
            continue
        terms.append(w if ("_" in w or any(c.isupper() for c in w)) else lw)
    # Deduplicate while preserving order (dict.fromkeys idiom).
    return list(dict.fromkeys(terms))


def _keyword_search(terms: list[str], k: int, engine: Engine) -> list[dict]:
    """Simple ILIKE search: chunks containing any of the terms.

    Ranked by (number of distinct terms matched, then shorter content
    first) — enough ranking signal for fusion at this corpus size
    (~1400 chunks). A full PostgreSQL tsvector/GIN setup would be the
    production-grade version; this is an honest, simpler trade-off
    documented in results.md.

    SECURITY NOTE: the f-string below only interpolates *parameter
    names* (:t0, :t1, ...) into the SQL — the actual term values all
    travel as bound parameters, so this is injection-safe.
    """
    if not terms:
        return []
    # Build "content ILIKE :t0 OR content ILIKE :t1 ..." dynamically
    # — one condition per term, values bound separately.
    conditions = " OR ".join(
        f"content ILIKE :t{i}" for i in range(len(terms)))
    params: dict = {}
    for i, t in enumerate(terms):
        params[f"t{i}"] = f"%{t}%"
    # Fetch extra candidates (2k) so fusion has material to work with
    # — the vector list also feeds 2k candidates in.
    params["k"] = k * 2

    # term_hits = how many distinct terms this chunk contains — the
    # primary ranking signal for the keyword list.
    sql = text(f"""
        SELECT page_url, page_title, heading_path, content,
               ({" + ".join(f"(CASE WHEN content ILIKE :t{i} THEN 1 ELSE 0 END)" for i in range(len(terms)))}) AS term_hits
        FROM chunks
        WHERE {conditions}
        ORDER BY term_hits DESC, LENGTH(content) ASC
        LIMIT :k
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [
        {"page_url": r[0], "page_title": r[1], "heading_path": r[2],
         "content": r[3], "term_hits": r[4]}
        for r in rows
    ]


def hybrid_search(query: str, k: int = 5, engine: Engine | None = None) -> list[HybridHit]:
    """Vector search + keyword search, fused with RRF.

    Both lists fetch 2k candidates (wider than the final k) so the
    fusion step has overlap to discover — fusing two already-truncated
    top-k lists would lose exactly the borderline documents that fusion
    is meant to rescue.

    Deduplication key is (page_url, heading_path): the same chunk
    reached through both lists must merge its scores, while two
    different chunks of one page stay separate entries.

    Args:
        query: natural-language question.
        k: final number of results.
        engine: optional injected engine (tests); defaults to shared engine.

    Returns:
        Up to k HybridHit, best RRF score first.
    """
    engine = engine or get_engine()

    # --- List 1: vector results (same SQL as app.rag.retriever) ---
    query_vec = embed_texts([query])[0]
    qv = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"
    vec_sql = text("""
        SELECT page_url, page_title, heading_path, content,
               1 - (embedding <=> CAST(:qv AS vector)) AS similarity
        FROM chunks
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :k
    """)
    with engine.connect() as conn:
        vrows = conn.execute(vec_sql, {"qv": qv, "k": k * 2}).all()
    vec_list = [
        {"page_url": r[0], "page_title": r[1], "heading_path": r[2],
         "content": r[3], "similarity": float(r[4])}
        for r in vrows
    ]

    # --- List 2: keyword results ---
    kw_list = _keyword_search(_keyword_terms(query), k, engine)

    # --- Fuse with RRF ---
    scores: dict[tuple, dict] = {}

    # Vector contributions: rank 1 of the vector list adds 1/(60+1).
    for rank, item in enumerate(vec_list, start=1):
        key = (item["page_url"], item["heading_path"])
        d = scores.setdefault(key, {**item, "rrf_score": 0.0,
                                    "similarity": item["similarity"],
                                    "matched_by": "vector"})
        d["rrf_score"] += 1.0 / (RRF_K + rank)

    # Keyword contributions: if the doc is already known, this ADDS to
    # its score (the 'both' case — the fusion payoff); otherwise it
    # enters the pool as a keyword-only hit.
    for rank, item in enumerate(kw_list, start=1):
        key = (item["page_url"], item["heading_path"])
        if key in scores:
            scores[key]["rrf_score"] += 1.0 / (RRF_K + rank)
            scores[key]["matched_by"] = "both"
        else:
            scores[key] = {**item, "similarity": 0.0, "rrf_score": 0.0,
                           "matched_by": "keyword"}

    # Final ranking by fused score; truncate to k.
    ranked = sorted(scores.values(),
                    key=lambda d: d["rrf_score"], reverse=True)

    hits = [
        HybridHit(
            page_url=d["page_url"], page_title=d["page_title"],
            heading_path=d["heading_path"], content=d["content"],
            similarity=d["similarity"], rrf_score=d["rrf_score"],
            matched_by=d["matched_by"],
        )
        for d in ranked[:k]
    ]
    logger.info("hybrid_search(%r, k=%d) → %d hits (%d both, %d kw-only)",
                query, k, len(hits),
                sum(1 for h in hits if h.matched_by == "both"),
                sum(1 for h in hits if h.matched_by == "keyword"))
    return hits
