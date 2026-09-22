#!/usr/bin/env python3
"""Compare pure-vector vs hybrid retrieval on the same 10 questions.

This is the 'measure the improvement' deliverable of the optional task:
both methods answer the SAME labeled questions, and the script reports
which questions each method hit — so the comparison is per-question,
not just one aggregate number. The output feeds the comparison table
in results.md.

Prerequisite: `python -m scripts.index` must have been run (config A).
"""
# isort: skip_file
from __future__ import annotations
from app.rag.hybrid import hybrid_search
from app.rag.retriever import search as vector_search
from app.evaluation.questions import QUESTIONS
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# WARNING level: suppress library noise so the comparison table is
# the only thing on screen.
logging.basicConfig(level=logging.WARNING)


def hit_at_k(hits, expected: set, k: int) -> bool:
    """Same page-level metric as the main evaluation: any expected
    page among the top-k results."""
    return any(h.page_title in expected for h in hits[:k])


def main() -> None:
    vec_hits = hyb_hits = 0

    for q in QUESTIONS:
        expected = set(q.expected_page_titles)
        v = vector_search(q.question, k=3)
        h = hybrid_search(q.question, k=3)
        vh, hh = hit_at_k(v, expected, 3), hit_at_k(h, expected, 3)
        vec_hits += vh
        hyb_hits += hh

        # Column legend: [VH] — V = vector hit, H = hybrid hit.
        # Explicit flags for regressions: an honest comparison must
        # show where the new method made things WORSE, not only better.
        flag = "  ← improved" if hh and not vh else (
            "  ← worse!" if vh and not hh else "")
        print(
            f"{'✅' if hh else '❌'} [{('V' if vh else ' ')}{('H' if hh else ' ')}] {q.question}{flag}")

    print("\n" + "=" * 50)
    print(f"Vector only : hit@3 = {vec_hits}/10")
    print(f"Hybrid      : hit@3 = {hyb_hits}/10")


if __name__ == "__main__":
    main()
