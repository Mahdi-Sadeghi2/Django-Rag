"""HTTP fetching with disk caching and polite-crawling behavior.

Responsibilities:
- download pages from docs.djangoproject.com (with delay + User-Agent)
- cache raw HTML on disk so re-runs don't touch the site at all
- discover the list of topic page URLs to crawl

The raw HTML is cached, *not* the extracted text: if the extraction
logic changes (as it did when we kept admonitions), re-processing
works from the local cache without a single new HTTP request.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)


class PageFetcher:
    """Downloads pages (with cache) and discovers topic URLs."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        user_agent: str | None = None,
        delay_seconds: float | None = None,
    ):
        # Constructor parameters allow tests to inject a temp cache dir
        # or zero delay; production falls back to global settings.
        self.cache_dir = cache_dir or settings.cache_dir
        self.user_agent = user_agent or settings.user_agent
        self.delay_seconds = delay_seconds if delay_seconds is not None else settings.request_delay_seconds
        # One Session = connection reuse (faster, kinder to the server)
        # and a single place to set the identifying User-Agent header
        # (polite-crawling requirement: the site can recognize us).
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        # Ensure the cache directory exists on first use.
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Timestamp of the last network request — used to enforce the
        # delay between consecutive downloads.
        self._last_request_time: float = 0.0

    def _cache_path(self, url: str) -> Path:
        """Map a URL to a stable, filesystem-safe cache file path.

        - A short sha256 of the URL guarantees uniqueness (two pages
          with the same last path segment would otherwise collide).
        - The human-readable path part makes files identifiable when
          browsing data/cache by eye.
        - Both parts are length-limited to respect Windows path limits.
        """
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        path_part = urlparse(url).path.strip("/").replace("/", "_") or "index"
        if len(path_part) > 80:
            path_part = path_part[:80]
        return self.cache_dir / f"{path_part}_{url_hash}.html"

    def _respect_delay(self) -> None:
        """Sleep if we are requesting faster than the configured rate.

        Polite-crawling requirement: never hammer the docs site. Only
        applies before *network* requests — cache hits are instant and
        delay-free by design.
        """
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def fetch(self, url: str, force: bool = False) -> str | None:
        """Return the HTML for a URL — from cache if possible.

        Returns None on network failure; the caller treats that as
        "this page failed" and continues (no crash, just a counter).
        `force=True` bypasses the cache (used when re-downloading).
        """
        cache_file = self._cache_path(url)

        # Cache hit: serve from disk, zero network cost, zero delay.
        if not force and cache_file.exists():
            logger.info("Cache hit: %s", url)
            return cache_file.read_text(encoding="utf-8", errors="replace")

        self._respect_delay()
        try:
            logger.info("Downloading: %s", url)
            response = self.session.get(url, timeout=30)
            # raise_for_status turns HTTP 4xx/5xx into exceptions so a
            # missing page is handled as an error, not stored as HTML.
            response.raise_for_status()
            html = response.text
            # Persist before returning: the next run gets a cache hit.
            cache_file.write_text(html, encoding="utf-8")
            self._last_request_time = time.time()
            return html
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            return None

    def discover_topic_links(self, index_url: str | None = None) -> list[str]:
        """Collect topic-page URLs starting from the topics index page.

        Strategy: try several containers in order of specificity —
        Sphinx's toctree first (the official list of topic pages),
        then generic main-content containers. The first container that
        yields enough links wins; this keeps us resilient if the site
        markup changes.

        Filters applied to every candidate link:
        - same domain only (djangoproject.com)
        - path must contain /topics/
        - drop the query string/fragment; normalize trailing slash so
          the same page is never visited twice with different URLs
        - skip the index page itself
        - skip foreign-language versions of the docs
        - deduplicate while preserving discovery order

        Returns a list (capped later by settings.max_pages).
        """
        index_url = index_url or settings.base_url
        html = self.fetch(index_url)
        if not html:
            logger.error("Could not load topics index: %s", index_url)
            return []

        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []

        # Ordered from most specific to most generic container.
        containers = [
            soup.select_one("div.toctree-wrapper"),
            soup.find("div", {"id": "main-content"}),
            soup.find("main"),
            soup.body,
        ]

        for container in containers:
            if container is None:
                continue
            for a in container.find_all("a", href=True):
                href = a["href"]
                # Pure in-page anchors point to the same page — skip.
                if href.startswith("#"):
                    continue

                # Resolve relative hrefs ("../db/models/") against the
                # index URL to get absolute links.
                full_url = urljoin(index_url, href)
                parsed = urlparse(full_url)

                # Stay on the official docs domain, topics section only.
                if not parsed.netloc.endswith("djangoproject.com"):
                    continue
                if "/topics/" not in parsed.path:
                    continue

                # Canonical form: no query string, no fragment, exactly
                # one trailing slash — makes deduplication reliable.
                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip(
                    "/") + "/"

                # Skip the index page itself.
                if clean.rstrip("/") == index_url.rstrip("/"):
                    continue
                # Skip translated docs (we only want the English corpus).
                if any(x in clean for x in (
                    "/zh-", "/ja/", "/ko/", "/pt-", "/es/", "/fr/",
                    "/it/", "/pl/", "/sv/", "/id/", "/de/", "/nl/",
                )):
                    continue

                if clean not in links:
                    links.append(clean)

            # Enough links found from a good container — stop widening.
            if len(links) > 20:
                break

        logger.info("Discovered %d topic links", len(links))
        return links
