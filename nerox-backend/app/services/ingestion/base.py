"""
app/services/ingestion/base.py
================================
Base classes and data types for the pluggable ingestion layer.

Every ingestion source module must implement `BaseSource.search()`.
This ensures a consistent interface so new sources can be added
without modifying the pipeline core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"

class SourceType(str, Enum):
    YOUTUBE = "youtube"
    WEB = "web"
    DYNAMIC_WEB = "dynamic_web"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    NEWS = "news"


@dataclass
class MediaItem:
    """
    A single piece of external media discovered during ingestion.

    Attributes:
        url:            Direct URL to the media (image src or video page).
        title:          Human-readable title or alt-text.
        thumbnail_url:  Thumbnail image URL (for videos).
        source_platform: Name of the platform (youtube, website, etc.).
        media_type:     MediaType.IMAGE or MediaType.VIDEO.
        metadata:       Extra info (duration, resolution, channel name, etc.).
    """
    url:              str
    title:            str = ""
    thumbnail_url:    Optional[str] = None
    source_platform:  str = SourceType.WEB.value
    media_type:       MediaType = MediaType.IMAGE
    metadata:         dict = field(default_factory=dict)


class BaseSource(ABC):
    """
    Abstract base class for all ingestion sources.

    Subclasses must implement `search()` which returns a list of MediaItems.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name (e.g., 'YouTube', 'Web Scraper')."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[MediaItem]:
        """
        Search the external source for media matching the query.

        Args:
            query:       Search term or URL to scan.
            max_results: Maximum number of items to return.

        Returns:
            List of MediaItem objects found.
        """
