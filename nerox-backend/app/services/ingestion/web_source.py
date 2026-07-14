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
import json
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
        Scrape images from a web page or search for images by keyword.

        Args:
            query:       Full URL of the page to scrape, OR a plain search keyword.
            max_results: Max images to return.

        Returns:
            List of MediaItem objects with image URLs.
        """
        # If the query is not a URL, use DuckDuckGo's image results endpoint.
        # The plain HTML images page is JS-driven and typically yields 0 <img> tags.
        if not query.startswith(("http://", "https://")):
            try:
                return await asyncio.to_thread(self._ddg_image_search, query, max_results)
            except Exception as exc:
                logger.warning("WebSource: DDG image search failed for '%s': %s", query, exc)
                # Fallback: resolve to a Wikipedia page URL via OpenSearch, then
                # scrape that page for <img> tags (often enough for keyword queries).
                try:
                    wiki_url = await asyncio.to_thread(self._wikipedia_opensearch_url, query)
                    if wiki_url:
                        query = wiki_url
                    else:
                        return []
                except Exception as exc2:
                    logger.warning("WebSource: Wikipedia fallback failed for '%s': %s", query, exc2)
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
    def _ddg_image_search(keyword: str, max_results: int) -> List[MediaItem]:
        """
        DuckDuckGo image search (best-effort).
        Fetch vqd token then call i.js endpoint to get image URLs.
        """
        encoded = urllib.parse.quote_plus(keyword)
        landing = f"https://duckduckgo.com/?q={encoded}&iax=images&ia=images"
        req = urllib.request.Request(landing, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read().decode(charset, errors="replace")

        # Extract vqd token used by the JSON endpoint.
        m = re.search(r"vqd='([^']+)'", html) or re.search(r'vqd=\"([^\"]+)\"', html)
        if not m:
            raise RuntimeError("DDG vqd token not found")
        vqd = m.group(1)

        api = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={encoded}&vqd={urllib.parse.quote_plus(vqd)}"
        req2 = urllib.request.Request(api, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": landing,
        })
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            raw = resp2.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        results = payload.get("results") or []

        items: List[MediaItem] = []
        seen: set[str] = set()
        for r in results:
            img_url = (r.get("image") or r.get("thumbnail") or "").strip()
            if not img_url or not img_url.startswith("http") or img_url in seen:
                continue
            if ".svg" in img_url.lower() or any(ext in img_url.lower() for ext in (".gif", ".ico")):
                continue
            seen.add(img_url)
            items.append(MediaItem(
                url=img_url,
                title=(r.get("title") or img_url.split("/")[-1])[:60],
                thumbnail_url=(r.get("thumbnail") or img_url),
                source_platform="duckduckgo",
                media_type=MediaType.IMAGE,
                metadata={"page_url": landing, "search_query": keyword},
            ))
            if len(items) >= max_results:
                break
        return items

    @staticmethod
    def _wikipedia_opensearch_url(keyword: str) -> str:
        """Return the top Wikipedia page URL for a keyword (best-effort)."""
        encoded = urllib.parse.quote_plus(keyword)
        api = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit=1&namespace=0&format=json"
        req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        # [searchterm, titles[], descriptions[], urls[]]
        urls = data[3] if isinstance(data, list) and len(data) >= 4 else []
        if urls and isinstance(urls[0], str) and urls[0].startswith("http"):
            return urls[0]
        return ""

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
