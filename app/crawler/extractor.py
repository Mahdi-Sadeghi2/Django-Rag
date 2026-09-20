from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag

from app.models import Heading, Page

logger = logging.getLogger(__name__)

# آستانه‌ی حداقل طول محتوا — صفحات index بخش Topics پس از حذف ناوبری
# فقط ۵۰ تا ۲۵۰ کاراکتر باقی می‌گذارند، در حالی که کوتاه‌ترین صفحه‌ی
# محتوایی بیش از ۲۰۰۰ کاراکتر دارد. (مستند: README → تصمیم‌های طراحی)
MIN_CONTENT_CHARS = 500

REMOVE_SELECTORS = [
    "nav", "header", "footer",
    ".sidebar", ".sphinxsidebar", "#sidebar",
    ".wy-nav-side", ".wy-side-scroll", ".wy-menu",
    ".toctree-wrapper", ".toc",
    ".breadcrumb", ".breadcrumbs", ".headerlink",
    "script", "style", "noscript",
    ".contents",
    "[role='navigation']", "[role='search']",
    # نکته: .admonition عمداً حذف شده — این باکس‌ها (note/warning/
    # versionadded) اطلاعات ارزشمندی دارند و با برچسب استخراج می‌شوند.
]

# تگ‌هایی که متنشان به‌عنوان پاراگراف محتوایی جمع می‌شود
CONTENT_TAGS = {"p", "li", "pre", "blockquote", "dt", "dd"}

# تگ‌های سرفصل که با # علامت‌گذاری می‌شوند
HEADING_TAGS = {"h1", "h2", "h3", "h4"}


class ContentExtractor:
    def extract(self, html: str, url: str) -> Page | None:
        try:
            soup = BeautifulSoup(html, "lxml")
            self._remove_noise(soup)

            title = self._extract_title(soup)
            headings = self._extract_headings(soup)
            content = self._extract_main_text(soup)

            if not content or len(content.strip()) < MIN_CONTENT_CHARS:
                logger.warning(
                    "Extracted content too short (%d chars) for %s — skipping "
                    "(likely an index/landing page)",
                    len(content or ""), url,
                )
                return None

            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            return Page(
                url=url,
                title=title,
                content=content,
                headings=headings,
                scraped_at=datetime.now(timezone.utc),
                content_hash=content_hash,
            )
        except Exception as exc:
            logger.error("Extraction failed for %s: %s", url, exc)
            return None

    def _remove_noise(self, soup: BeautifulSoup) -> None:
        for selector in REMOVE_SELECTORS:
            for tag in soup.select(selector):
                tag.decompose()

    def _extract_title(self, soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        if h1:
            return self._clean_text(h1.get_text())
        if soup.title:
            return self._clean_text(soup.title.get_text())
        return "Untitled"

    def _extract_headings(self, soup: BeautifulSoup) -> list[Heading]:
        headings: list[Heading] = []
        for level in range(1, 4):
            for tag in soup.find_all(f"h{level}"):
                text = self._clean_text(tag.get_text())
                if text:
                    headings.append(Heading(level=level, text=text))
        return headings

    def _extract_admonitions(self, soup: BeautifulSoup) -> list[str]:
        results: list[str] = []
        for div in soup.select("div.admonition"):
            classes = div.get("class", [])
            kind = next((c for c in classes if c != "admonition"), "note")
            # فقط باکس‌های متنی استاندارد — باکس‌های کد را همان‌جا نگه می‌داریم
            if kind in {"note", "warning", "seealso", "caution",
                        "danger", "error", "hint", "important", "tip",
                        "admonition", "versionadded", "versionchanged", "deprecated"}:
                text = self._clean_text(div.get_text())
                if text:
                    results.append(f"> [{kind}] {text}")
                div.decompose()
        return results

    def _extract_main_text(self, soup: BeautifulSoup) -> str:
        main = (
            soup.find("div", {"id": "main-content"})
            or soup.find("div", {"role": "main"})
            or soup.find("article")
            or soup.find("div", class_="document")
            or soup.body
        )
        if not main:
            return ""

        # باکس‌های admonition جداگانه جمع می‌شوند (و از درخت حذف می‌شوند)
        admonitions = self._extract_admonitions(main)

        lines: list[str] = []
        for element in main.descendants:
            if isinstance(element, NavigableString):
                continue
            if not isinstance(element, Tag):
                continue

            if element.name in CONTENT_TAGS:
                text = self._clean_text(element.get_text())
                if text:
                    lines.append(text)
            elif element.name in HEADING_TAGS:
                text = self._clean_text(element.get_text())
                if text:
                    lines.append(f"\n{'#' * int(element.name[1])} {text}\n")

        if len(lines) < 3:
            body = self._clean_text(main.get_text(separator="\n"))
        else:
            body = "\n\n".join(lines).strip()

        # باکس‌ها در انتهای محتوا اضافه می‌شوند تا hash و ذخیره هم‌خوان بمانند
        if admonitions:
            body = body + "\n\n" + "\n\n".join(admonitions)

        return body

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()
