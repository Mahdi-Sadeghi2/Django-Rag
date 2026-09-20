#!/usr/bin/env python3
# isort: skip_file
from __future__ import annotations
from app.evaluation.runner import run_evaluation
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING)  # خروجی تمیز برای گزارش


def main() -> None:
    print("=" * 60)
    r3 = run_evaluation(k=3)
    print(f"hit@3 (صفحه‌محور): {r3['hit_rate']:.0%}")
    print("=" * 60)

    # جزئیات هر پرسش — برای تحلیل در results.md
    for r in r3["results"]:
        mark = "✅" if r["hit"] else "❌"
        top = r["hits"][0]
        print(f"\n{mark} {r['question']}")
        print(
            f"   top: [{top.similarity:.3f}] {top.page_title} — {top.heading_path}")


if __name__ == "__main__":
    main()
