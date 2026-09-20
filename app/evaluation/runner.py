from __future__ import annotations

import logging

from app.evaluation.questions import QUESTIONS, EvalQuestion
from app.rag.retriever import search

logger = logging.getLogger(__name__)


def hit_at_k(question: EvalQuestion, k: int = 3) -> tuple[bool, list]:
    """آیا در k نتیجه‌ی اول، حداقل یکی از صفحات مورد انتظار هست؟"""
    hits = search(question.question, k=k)
    expected = set(question.expected_page_titles)
    hit = any(h.page_title in expected for h in hits)
    return hit, hits


def run_evaluation(k: int = 3, quiet: bool = True) -> dict:
    """ارزیابی همه‌ی پرسش‌ها با معیار hit@k (بر اساس صفحه)."""
    results = []
    for q in QUESTIONS:
        hit, hits = hit_at_k(q, k=k)
        if not quiet:
            print(f"\nQ: {q.question}")
            for h in hits:
                mark = "✓" if h.page_title in q.expected_page_titles else " "
                print(
                    f"  {mark} [{h.similarity:.3f}] {h.page_title} — {h.heading_path}")
        results.append({"question": q.question, "hit": hit, "hits": hits})

    hit_rate = sum(r["hit"] for r in results) / len(results)
    return {"k": k, "hit_rate": hit_rate, "results": results}
