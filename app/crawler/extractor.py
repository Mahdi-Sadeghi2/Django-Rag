"""HTML -> clean text extraction for the Django documentation pages.

Turns raw Sphinx HTML into a Page model containing:
- the page title,
- the h1-h3 outline (kept per task requirements),
- the cleaned main text (navigation removed, code blocks kept,
  admonition boxes preserved with a type label),
- a sha256 content hash used for idempotent upserts.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag

from app.models import Heading, Page

logger = logging.getLogger(__name__)

# Minimum length of extracted content to keep a page.
# Data-driven threshold: index/landing pages of the Topics section leave
# only 50-250 chars after noise removal, while the 10th percentile of
# real content pages is 2618 chars. 500 sits safely inside that gap.
# (Documented in README -> design decisions.)
MIN_CONTENT_CHARS = 500

# CSS selectors for everything that is NOT documentation content:
# navigation, sidebars, tables of contents, breadcrumbs, scripts.
# Removing these BEFORE extracting text is what turns a full HTML page
# into clean documentation text.
REMOVE_SELECTORS = [
    "nav", "header", "footer",
    ".sidebar", ".sphinxsidebar", "#sidebar",
    ".wy-nav-side", ".wy-side-scroll", ".wy-menu",
    ".toctree-wrapper", ".toc",
    ".breadcrumb", ".breadcrumbs", ".headerlink",
    "script", "style", "noscript",
    ".contents",
    "[role='navigation']", "[role='search']",
    # NOTE: .admonition is deliberately NOT in this list. These boxes
    # (note/warning/versionadded) carry valuable information — security
    # warnings, version compatibility — so they are extracted with a
    # type label instead of being deleted (an earlier version removed
    # them; reviewing the pages showed real information was being lost).
]

# Tags whose text is collected as content paragraphs.
# Includes <pre> (code blocks: essential for technical Q&A) and
# dt/dd (definition lists, common in technical docs).
CONTENT_TAGS = {"p", "li", "pre", "blockquote", "dt", "dd"}

# Heading tags rendered with markdown-style '#' markers in the text —
# these markers later drive the heading-aware chunking.
HEADING_TAGS = {"h1", "h2", "h3", "h4"}


class ContentExtractor:
    """Extracts a Page model from raw documentation HTML."""

    def extract(self, html: str, url: str) -> Page | None:
        """Main entry point: raw HTML -> Page (or None if rejected).

        Returns None (never raises) for two cases:
        - content too short: an index/landing page, filtered on purpose
        - any unexpected parsing error: the crawler logs and continues
        """
        try:
            soup = BeautifulSoup(html, "lxml")  # lxml: fast, lenient parser
            # Strip navigation/noise from the whole document first.
            self._remove_noise(soup)

            title = self._extract_title(soup)
            headings = self._extract_headings(soup)
            content = self._extract_main_text(soup)

            # Reject pages with no real content (index/landing pages).
            if not content or len(content.strip()) < MIN_CONTENT_CHARS:
                logger.warning(
                    "Extracted content too short (%d chars) for %s — skipping "
                    "(likely an index/landing page)",
                    len(content or ""), url,
                )
                return None

            # sha256 of the final text — the fingerprint used by the
            # repository upsert to detect pages that actually changed.
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
        """Remove all noise elements listed in REMOVE_SELECTORS."""
        for selector in REMOVE_SELECTORS:
            for tag in soup.select(selector):
                tag.decompose()  # decompose: remove from tree AND free memory

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Prefer the h1 (the real page title); fall back to <title>."""
        h1 = soup.find("h1")
        if h1:
            return self._clean_text(h1.get_text())
        if soup.title:
            return self._clean_text(soup.title.get_text())
        return "Untitled"

    def _extract_headings(self, soup: BeautifulSoup) -> list[Heading]:
        """Collect the h1-h3 outline (task requirement: keep headings).

        Stored separately in the pages table as JSONB, in document order.
        """
        headings: list[Heading] = []
        for level in range(1, 4):
            for tag in soup.find_all(f"h{level}"):
                text = self._clean_text(tag.get_text())
                if text:
                    headings.append(Heading(level=level, text=text))
        return headings

    def _extract_admonitions(self, soup: BeautifulSoup) -> list[str]:
        """Extract Sphinx admonition boxes as labeled text lines.

        Each standard box (note, warning, versionadded, ...) becomes
        '> [kind] text'. The div is then decomposed so the main-text
        loop cannot pick up its inner <p>/<li> elements again — this
        prevents double-counting (the box text appearing both as a
        labeled line and as regular paragraphs).

        Non-standard divs (e.g. code-only boxes) are left in the tree
        untouched: the main loop extracts them as ordinary content.
        """
        results: list[str] = []
        for div in soup.select("div.admonition"):
            classes = div.get("class", [])
            # The kind is the class that is not the generic 'admonition',
            # e.g. <div class="admonition warning"> -> 'warning'.
            kind = next((c for c in classes if c != "admonition"), "note")
            # Whitelist of standard Sphinx kinds — keeps exotic divs out.
            if kind in {"note", "warning", "seealso", "caution",
                        "danger", "error", "hint", "important", "tip",
                        "admonition", "versionadded", "versionchanged", "deprecated"}:
                text = self._clean_text(div.get_text())
                if text:
                    results.append(f"> [{kind}] {text}")
                div.decompose()
        return results

    def _extract_main_text(self, soup: BeautifulSoup) -> str:
        """Build the cleaned main text from the page's main container.

        Tries several increasingly generic containers (Sphinx-specific
        first) so a markup change degrades gracefully instead of
        returning nothing.
        """
        main = (
            soup.find("div", {"id": "main-content"})
            or soup.find("div", {"role": "main"})
            or soup.find("article")
            or soup.find("div", class_="document")
            or soup.body
        )
        if not main:
            return ""

        # Admonitions are harvested (and removed from the tree) first.
        admonitions = self._extract_admonitions(main)

        lines: list[str] = []
        # Walk every element in document order; keep only content tags
        # and headings. NavigableString is skipped because plain text
        # nodes belong to their parent paragraph (already captured via
        # get_text on the parent tag).
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
                # '## ' prefix (one '#' per heading level) marks section
                # boundaries in the stored text — the chunker later
                # splits exactly on these markers.
                text = self._clean_text(element.get_text())
                if text:
                    lines.append(f"\n{'#' * int(element.name[1])} {text}\n")

        # Fallback: if structured extraction produced almost nothing
        # (unusual markup), keep the raw text rather than losing the page.
        if len(lines) < 3:
            body = self._clean_text(main.get_text(separator="\n"))
        else:
            body = "\n\n".join(lines).strip()

        # Admonitions are appended at the end so the hash and stored
        # content stay consistent regardless of where boxes sat in HTML.
        if admonitions:
            body = body + "\n\n" + "\n\n".join(admonitions)

        return body

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse all whitespace runs (newlines, tabs, multi-spaces —
        common in formatted HTML) into single spaces and trim."""
        text = re.sub(r"\s+", " ", text)
        return text.strip()
