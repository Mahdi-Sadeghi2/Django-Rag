# isort: skip_file
from app.rag.retriever import search
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)


for q in [
    "How do I write a custom middleware?",
    "What is get_absolute_url used for?",
    "how to cache a view",
]:
    print("\n" + "=" * 70)
    print("Q:", q)
    for hit in search(q, k=3):
        print(f"  [{hit.similarity:.3f}] {hit.page_title} — {hit.heading_path}")
        print(f"      {hit.content[:120]}...")
