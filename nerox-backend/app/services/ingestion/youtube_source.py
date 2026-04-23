"""
app/services/ingestion/youtube_source.py
==========================================
YouTube Data API v3 ingestion source for Phase 2.5.

Searches YouTube for videos matching a query string, returns structured
MediaItem results with title, thumbnail, and video URL.

Rate-limit safety:
  - Respects AUTO_SCAN_REQUEST_DELAY between API calls
  - Limits results to max_results (capped at 50 per API spec)
  - Logs all external requests for audit trail

Requirements:
  - YOUTUBE_API_KEY must be set in .env
  - No additional pip packages needed (uses stdlib httpx-compatible aiohttp or urllib)
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.parse
from typing import List

from app.core.config import settings
from app.core.logger import get_logger
from app.services.ingestion.base import BaseSource, MediaItem, MediaType

logger = get_logger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YouTubeSource(BaseSource):
    """YouTube Data API v3 search source."""

    @property
    def name(self) -> str:
        return "YouTube"

    async def search(self, query: str, max_results: int = 10) -> List[MediaItem]:
        """
        Search YouTube for videos matching `query`.

        Uses the YouTube Data API v3 `search.list` endpoint.
        Falls back gracefully if the API key is missing or invalid.

        Args:
            query:       Search keywords.
            max_results: Max videos to return (capped at 50).

        Returns:
            List of MediaItem objects with video URLs and thumbnails.
        """
        api_key = settings.YOUTUBE_API_KEY
        if not api_key:
            logger.warning("YouTube API key not configured — skipping YouTube source.")
            return []

        max_results = min(max_results, 50)  # API limit

        params = urllib.parse.urlencode({
            "part":       "snippet",
            "q":          query,
            "type":       "video",
            "maxResults": max_results,
            "key":        api_key,
            "order":      "relevance",
        })
        url = f"{YOUTUBE_SEARCH_URL}?{params}"

        logger.info(
            "YouTube search — query='%s' max_results=%d",
            query, max_results,
        )

        try:
            # Run blocking HTTP in thread pool to avoid blocking the event loop
            data = await asyncio.to_thread(self._fetch_json, url)
        except Exception as exc:
            logger.error("YouTube API request failed: %s", exc)
            return []

        items: List[MediaItem] = []
        for entry in data.get("items", []):
            video_id = entry.get("id", {}).get("videoId")
            if not video_id:
                continue

            snippet = entry.get("snippet", {})
            thumb = (
                snippet.get("thumbnails", {})
                .get("high", {})
                .get("url")
                or snippet.get("thumbnails", {})
                .get("default", {})
                .get("url", "")
            )

            items.append(MediaItem(
                url=f"https://www.youtube.com/watch?v={video_id}",
                title=snippet.get("title", ""),
                thumbnail_url=thumb,
                source_platform="youtube",
                media_type=MediaType.VIDEO,
                metadata={
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", "")[:200],
                },
            ))

            # Respect rate-limit delay between processing items
            await asyncio.sleep(settings.AUTO_SCAN_REQUEST_DELAY * 0.1)

        logger.info("YouTube search returned %d results for query='%s'", len(items), query)
        return items

    @staticmethod
    def _fetch_json(url: str) -> dict:
        """Synchronous HTTP GET → parsed JSON (runs in thread pool)."""
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
