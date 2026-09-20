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
    def __init__(
        self,
        cache_dir: Path | None = None,
        user_agent: str | None = None,
        delay_seconds: float | None = None,
    ):
        self.cache_dir = cache_dir or settings.cache_dir
        self.user_agent = user_agent or settings.user_agent
        self.delay_seconds = delay_seconds if delay_seconds is not None else settings.request_delay_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request_time: float = 0.0

    def _cache_path(self, url: str) -> Path:
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        path_part = urlparse(url).path.strip("/").replace("/", "_") or "index"
        if len(path_part) > 80:
            path_part = path_part[:80]
        return self.cache_dir / f"{path_part}_{url_hash}.html"

    def _respect_delay(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def fetch(self, url: str, force: bool = False) -> str | None:
        cache_file = self._cache_path(url)

        if not force and cache_file.exists():
            logger.info("Cache hit: %s", url)
            return cache_file.read_text(encoding="utf-8", errors="replace")

        self._respect_delay()
        try:
            logger.info("Downloading: %s", url)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html = response.text
            cache_file.write_text(html, encoding="utf-8")
            self._last_request_time = time.time()
            return html
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            return None

    def discover_topic_links(self, index_url: str | None = None) -> list[str]:
        index_url = index_url or settings.base_url
        html = self.fetch(index_url)
        if not html:
            logger.error("Could not load topics index: %s", index_url)
            return []

        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []

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
                if href.startswith("#"):
                    continue

                full_url = urljoin(index_url, href)
                parsed = urlparse(full_url)

                if not parsed.netloc.endswith("djangoproject.com"):
                    continue
                if "/topics/" not in parsed.path:
                    continue

                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip(
                    "/") + "/"

                if clean.rstrip("/") == index_url.rstrip("/"):
                    continue
                if any(x in clean for x in (
                    "/zh-", "/ja/", "/ko/", "/pt-", "/es/", "/fr/",
                    "/it/", "/pl/", "/sv/", "/id/", "/de/", "/nl/",
                )):
                    continue

                if clean not in links:
                    links.append(clean)

            if len(links) > 20:
                break

        logger.info("Discovered %d topic links", len(links))
        return links
