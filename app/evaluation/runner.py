"""Evaluation runner: measures retrieval quality with hit@k.

Metric choice (documented in results.md): page-level hit@k — does at
least one of the expected pages appear among the top-k results? This
mirrors the real use case (the user follows the cited source) and is
more forgiving of chunk-boundary effects than exact-chunk matching.
"""

from __future__ import annotations

import logging

from app.evaluation.questions import QUESTIONS, EvalQuestion
from app.rag.retriever import search

logger = logging.getLogger(__name__)


def hit_at_k(question: EvalQuestion, k: int = 3) -> tuple[bool, list]:
    """Run one question: is any expected page among the top-k results?

    Returns (hit, hits) — the raw hits are kept so the caller can print
    the ranking details for the results.md report.
    """
    hits = search(question.question, k=k)
    expected = set(question.expected_page_titles)  # set: O(1) membership
    hit = any(h.page_title in expected for h in hits)
    return hit, hits


def run_evaluation(k: int = 3, quiet: bool = True) -> dict:
    """Evaluate all questions with the hit@k metric (page-level).

    Args:
        k: how many top results to consider.
        quiet: if False, prints the full per-question ranking to stdout
            (useful for interactive debugging).

    Returns:
        {"k": k, "hit_rate": fraction of hits in [0,1],
         "results": per-question {question, hit, hits} list}
    """
    results = []
    for q in QUESTIONS:
        hit, hits = hit_at_k(q, k=k)
        if not quiet:
            print(f"\nQ: {q.question}")
            for h in hits:
                # '✓' marks results whose page is an expected one.
                mark = "✓" if h.page_title in q.expected_page_titles else " "
                print(
                    f"  {mark} [{h.similarity:.3f}] {h.page_title} — {h.heading_path}")
        results.append({"question": q.question, "hit": hit, "hits": hits})

    # Simple mean of per-question booleans = fraction of questions hit.
    hit_rate = sum(r["hit"] for r in results) / len(results)
    return {"k": k, "hit_rate": hit_rate, "results": results}
