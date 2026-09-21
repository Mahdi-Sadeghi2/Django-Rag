"""سرور MCP برای جست‌وجوی معنایی در مستندات Django.

سه ابزار ارائه می‌دهد:
- search_docs: جست‌وجوی معنایی — وقتی کاربر درباره‌ی رفتار Django می‌پرسد
- get_page: دریافت متن کامل یک صفحه — وقتی URL یا عنوان صفحه معلوم است
- answer: پاسخ بر اساس تکه‌های بازیابی‌شده — پرسش مستقیم کاربر

توصیف هر ابزار برای مدل زبانیِ کلاینت نوشته شده تا بداند کِی صدایش بزند.
"""
from __future__ import annotations
from app.storage.database import get_readonly_engine
from app.rag.retriever import search as semantic_search
from app.config import settings
from mcp.server.mcpserver import MCPServer

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

mcp = MCPServer("django-docs-rag")

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = get_readonly_engine()
    return _engine


def _clip(text: str, limit: int) -> str:
    """برش متن با نشانه‌ی ادامه — سقف اندازه‌ی نتایج (الزام امنیتی)."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… [truncated]"


# ---------- ابزار ۱: search_docs ----------

@mcp.tool()
def search_docs(query: str, k: int = 5) -> str:
    """Semantic search over the official Django documentation (topics
    section). Use when the user asks how something works in Django or
    wants relevant documentation passages. Returns up to k chunks with
    page title, section heading path, URL and a similarity score (0..1).

    Args:
        query: Natural-language question or topic, e.g. 'how middleware works'.
        k: Number of results (1..10, default 5).
    """
    if not query or not query.strip():
        return "Error: 'query' must be a non-empty string."

    try:
        k = int(k)
    except (TypeError, ValueError):
        return "Error: 'k' must be an integer."
    k = max(1, min(k, settings.mcp_max_k))  # سقف امنیتی

    hits = semantic_search(query.strip(), k=k, engine=engine())
    if not hits:
        return ("No results found. The documentation index may be empty "
                "or the query may be outside the indexed topics section.")

    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"{i}. [{h.similarity:.3f}] {h.page_title} — {h.heading_path}\n"
            f"   URL: {h.page_url}\n"
            f"   {_clip(h.content, settings.mcp_max_content_chars)}"
        )
    return f"Top {len(hits)} results for: {query!r}\n\n" + "\n\n".join(lines)


# ---------- ابزار ۲: get_page ----------

@mcp.tool()
def get_page(url_or_id: str) -> str:
    """Return the full cleaned text of one documentation page by URL or
    exact page title. Use when you already know which page you need.

    Args:
        url_or_id: Page URL or exact page title, e.g. 'Middleware'.
    """
    if not url_or_id or not url_or_id.strip():
        return "Error: 'url_or_id' must be a non-empty string."

    from sqlalchemy import text

    ident = url_or_id.strip()
    sql = text("""
        SELECT url, title, content FROM pages
        WHERE url = :ident OR title = :ident
        LIMIT 1
    """)
    with engine().connect() as conn:
        row = conn.execute(sql, {"ident": ident}).first()

    if row is None:
        # پیام روشن، نه exception خام (الزام تسک)
        return (f"Page not found: {ident!r}. Tip: pass the exact page "
                f"title (e.g. 'Middleware') or the full URL as crawled "
                f"from docs.djangoproject.com.")

    url, title, content = row
    return (f"# {title}\n\nURL: {url}\n\n"
            f"{_clip(content, settings.mcp_max_content_chars)}")


# آستانه‌ی اطمینان: زیر این شباهت، نتیجه را «مرتبط» حساب نمی‌کنیم
# (از ارزیابی: پایین‌ترین امتیازِ موفق ۰.۴۸ بود — کمی محافظه‌کارتر)
MIN_CONFIDENCE = 0.45


# ---------- ابزار ۳: answer ----------

@mcp.tool()
def answer(question: str) -> str:
    """Answer a Django question using retrieved documentation chunks,
    with source citations. Uses semantic retrieval plus extractive
    synthesis (no external LLM). If nothing relevant is found, honestly
    says so.

    Args:
        question: The user's Django question.
    """
    if not question or not question.strip():
        return "Error: 'question' must be a non-empty string."

    hits = semantic_search(question.strip(), k=5, engine=engine())

    # الزام تسک: اگر پاسخی در تکه‌های بازیابی‌شده نبود، صادقانه بگو
    if not hits or hits[0].similarity < MIN_CONFIDENCE:
        best = f"{hits[0].similarity:.3f}" if hits else "n/a"
        return ("I could not find relevant documentation for this question "
                f"(best similarity: {best}). The indexed corpus covers only "
                "the 'topics' section of the Django documentation, so "
                "reference/guide pages may be missing. Please rephrase the "
                "question or search the Django docs directly.")

    # پاسخ استخراجی (بدون LLM خارجی): بهترین تکه‌ها با ارجاع
    parts = ["Answer based on the Django documentation "
             f"(top {len(hits)} passages):\n"]
    for i, h in enumerate(hits, 1):
        parts.append(
            f"\n[{i}] {h.page_title} — {h.heading_path} "
            f"(similarity {h.similarity:.3f})\n"
            f"    {_clip(h.content, 600)}\n"
            f"    Source: {h.page_url}"
        )
    parts.append("\nNote: this is an extractive answer assembled from the "
                 "passages above. For the full context, follow the source URLs.")
    return "\n".join(parts)


def run() -> None:
    """اجرای سرور روی stdio — ورودی استاندارد کلاینت‌های MCP."""
    mcp.run(transport="stdio")
