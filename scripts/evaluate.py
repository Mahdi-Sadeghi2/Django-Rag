
"""Run the retrieval evaluation and print a per-question report.

Produces the numbers that feed results.md: an overall hit@k rate plus
one line per question showing the top hit (score, page, heading path).
Task principle behind this script: "it works" is not enough — measure it.

NOTE: run `python -m scripts.index` first; the evaluation measures
whatever chunk configuration is currently indexed in the database.
"""
# isort: skip_file
from __future__ import annotations
from app.evaluation.runner import run_evaluation
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# WARNING level: library noise (embedding model loading, HF hub checks,
# per-search INFO lines) is suppressed so the printed report stays clean
# and copy-pasteable into results.md.
logging.basicConfig(level=logging.WARNING)


def main() -> None:
    print("=" * 60)
    # hit@3 page-level: does at least one of the expected pages appear
    # in the top-3 results? (k=3 is a realistic context-window budget.)
    r3 = run_evaluation(k=3)
    print(f"hit@3 (page-level): {r3['hit_rate']:.0%}")
    print("=" * 60)

    # Per-question detail — the ✅/❌ table plus the top hit's score,
    # page and heading path. This is what gets transcribed into the
    # results.md comparison table and drives the failure analysis.
    for r in r3["results"]:
        mark = "✅" if r["hit"] else "❌"
        top = r["hits"][0]
        print(f"\n{mark} {r['question']}")
        print(
            f"   top: [{top.similarity:.3f}] {top.page_title} — {top.heading_path}")


if __name__ == "__main__":
    main()
