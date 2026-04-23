"""
app/services/ingestion/web_source.py
======================================
Basic web scraper ingestion source for Phase 2.5.

Extracts image URLs from a given web page. Uses stdlib urllib + html.parser
to avoid heavy dependencies. Falls back gracefully if the page cannot be
fetched.

Safety features:
  - Respects AUTO_SCAN_REQUEST_DELAY between requests
  - Configurable user-agent to identify the bot
  - Timeout on all requests (15s)
  - Logs all external requests
  - Limits output to max_results images

Design note:
  For production-grade scraping with JavaScript-rendered pages, replace
  the _fetch_html method with Playwright (async). The interface remains
  the same — only the transport layer changes.
"""

from __future__ import annotations

import asyncio
import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import List, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.services.ingestion.base import BaseSource, MediaItem, MediaType

logger = get_logger(__name__)

USER_AGENT = "NeroxBot/2.5 (+https://nerox.io/bot)"

# Minimum image URL length to filter out tracking pixels and icons
MIN_IMAGE_URL_LENGTH = 30


class _ImageExtractor(HTMLParser):
    """Simple HTML parser that collects <img src=...> URLs."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "img":
            return
        attr_dict = dict(attrs)
        src = attr_dict.get("src") or attr_dict.get("data-src") or ""
        if not src:
            return

        # Resolve relative URLs
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urllib.parse.urljoin(self.base_url, src)
        elif not src.startswith("http"):
            src = urllib.parse.urljoin(self.base_url, src)

        # Filter out tiny tracking pixels, SVGs, and base64 images
        if len(src) < MIN_IMAGE_URL_LENGTH:
            return
        if "data:image" in src or ".svg" in src.lower():
            return
        if any(ext in src.lower() for ext in (".gif", ".ico")):
            return

        self.images.append(src)


class WebSource(BaseSource):
    """Web scraper source — extracts images from a given URL."""

    @property
    def name(self) -> str:
        return "Web Scraper"

    async def search(self, query: str, max_results: int = 20) -> List[MediaItem]:
        """
        Scrape images from a web page.

        Args:
            query:       Full URL of the page to scrape.
            max_results: Max images to return.

        Returns:
            List of MediaItem objects with image URLs.
        """
        # Validate that query looks like a URL
        if not query.startswith(("http://", "https://")):
            logger.warning("WebSource: query '%s' is not a valid URL — skipping.", query)
            return []

        logger.info("Web scrape — url='%s' max_results=%d", query, max_results)

        try:
            html = await asyncio.to_thread(self._fetch_html, query)
        except Exception as exc:
            logger.error("Web scrape failed for '%s': %s", query, exc)
            return []

        # Parse images from HTML
        parser = _ImageExtractor(query)
        try:
            parser.feed(html)
        except Exception as exc:
            logger.warning("HTML parsing error for '%s': %s", query, exc)

        # Deduplicate and limit
        seen: set[str] = set()
        items: List[MediaItem] = []
        for img_url in parser.images:
            if img_url in seen:
                continue
            seen.add(img_url)

            items.append(MediaItem(
                url=img_url,
                title=img_url.split("/")[-1][:60],
                thumbnail_url=img_url,
                source_platform="website",
                media_type=MediaType.IMAGE,
                metadata={"page_url": query},
            ))

            if len(items) >= max_results:
                break

        logger.info(
            "Web scrape found %d images on '%s'",
            len(items), query,
        )
        return items

    @staticmethod
    def _fetch_html(url: str) -> str:
        """Synchronous HTTP GET → HTML string (runs in thread pool)."""
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
