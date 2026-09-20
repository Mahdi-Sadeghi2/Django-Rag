from __future__ import annotations

from pathlib import Path

import pytest

from app.crawler.extractor import MIN_CONTENT_CHARS, ContentExtractor

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def extractor() -> ContentExtractor:
    return ContentExtractor()


@pytest.fixture()
def real_page_html() -> str:
    """یک صفحه‌ی واقعیِ ذخیره‌شده از docs.djangoproject.com — بدون اینترنت."""
    return (FIXTURES / "decorators.html").read_text(encoding="utf-8")


class TestRealPageExtraction:
    """تست‌ها روی HTML واقعی اجرا می‌شوند تا رفتار با ساختار Sphinx واقعی
    پوشش داده شود — نه فقط HTML ساختگی."""

    def test_extracts_substantial_content(self, extractor, real_page_html):
        url = "https://docs.djangoproject.com/en/stable/topics/http/decorators/"
        page = extractor.extract(real_page_html, url)

        assert page is not None, "صفحه‌ی واقعی نباید به‌عنوان index رد شود"
        assert len(page.content) >= MIN_CONTENT_CHARS
        assert page.title == "View decorators"

    def test_removes_navigation_noise(self, extractor, real_page_html):
        url = "https://docs.djangoproject.com/en/stable/topics/http/decorators/"
        page = extractor.extract(real_page_html, url)

        # این عبارات فقط در سایدبار/ناوبری وجود دارند نه متن اصلی
        assert "Toggle theme" not in page.content
        assert "Documentation" != page.title  # title ناوبری نباشد

    def test_preserves_admonitions_with_label(self, extractor, real_page_html):
        url = "https://docs.djangoproject.com/en/stable/topics/http/decorators/"
        page = extractor.extract(real_page_html, url)

        # این صفحه حداقل یک versionchanged دارد — با برچسب حفظ می‌شود
        assert "[version" in page.content or "[note]" in page.content

    def test_preserves_code_blocks(self, extractor, real_page_html):
        url = "https://docs.djangoproject.com/en/stable/topics/http/decorators/"
        page = extractor.extract(real_page_html, url)

        # این صفحه پر از import و decorator است — کد نباید از بین برود
        assert "from django" in page.content

    def test_rejects_index_page(self, extractor):
        """صفحه‌ی index (متنِ کوتاه بعد از حذف ناوبری) باید None برگرداند."""
        index_html = """
        <html><body>
          <nav><a href="/a/">A</a><a href="/b/">B</a></nav>
          <div id="main-content"><p>Overview of topics.</p></div>
        </body></html>
        """
        assert extractor.extract(
            index_html, "https://example.com/topics/") is None

    def test_content_hash_is_deterministic(self, extractor, real_page_html):
        url = "https://example.com/page/"
        p1 = extractor.extract(real_page_html, url)
        p2 = extractor.extract(real_page_html, url)
        assert p1.content_hash == p2.content_hash
