"""
app/services/ingestion/registry.py
=====================================
Phase 2.6 — Pluggable Source Registry.

Clean plugin registration system for ingestion sources. New sources
can be registered at import time or during app startup.

Usage:
    from app.services.ingestion.registry import source_registry, SourceType

    # Register a new source
    source_registry.register(SourceType.YOUTUBE, YouTubeSource())

    # Get a source
    src = source_registry.get(SourceType.YOUTUBE)

    # List all registered sources
    for name, src in source_registry.list_sources():
        print(f"{name}: {src.name}")
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.core.logger import get_logger
from app.services.ingestion.base import BaseSource, SourceType

logger = get_logger(__name__)


class SourceRegistry:
    """
    Thread-safe registry for ingestion source plugins.

    Sources are registered by SourceType and can be retrieved,
    listed, or checked for availability at runtime.
    """

    def __init__(self) -> None:
        self._sources: Dict[SourceType, BaseSource] = {}

    def register(self, source_type: SourceType, source: BaseSource) -> None:
        """Register an ingestion source plugin."""
        self._sources[source_type] = source
        logger.info(
            "Source registered: %s → %s",
            source_type.value, source.name,
        )

    def get(self, source_type: SourceType) -> Optional[BaseSource]:
        """Get a registered source by type. Returns None if not registered."""
        return self._sources.get(source_type)

    def get_by_name(self, name: str) -> Optional[BaseSource]:
        """Get a registered source by string name (e.g., 'youtube')."""
        try:
            st = SourceType(name)
            return self._sources.get(st)
        except ValueError:
            return None

    def is_available(self, source_type: SourceType) -> bool:
        """Check if a source type is registered and available."""
        return source_type in self._sources

    def list_sources(self) -> List[Tuple[str, BaseSource]]:
        """Return all registered sources as (name, instance) pairs."""
        return [(st.value, src) for st, src in self._sources.items()]

    def available_types(self) -> List[str]:
        """Return list of available source type strings."""
        return [st.value for st in self._sources.keys()]

    @property
    def count(self) -> int:
        """Number of registered sources."""
        return len(self._sources)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
source_registry = SourceRegistry()


def initialize_default_sources() -> None:
    """
    Register the default built-in sources.

    Called at app startup. New sources should be added here
    or registered dynamically via the registry API.
    """
    from app.services.ingestion.youtube_source import YouTubeSource
    from app.services.ingestion.web_source import WebSource
    from app.services.ingestion.playwright_source import PlaywrightSource
    from app.core.config import settings

    source_registry.register(SourceType.YOUTUBE, YouTubeSource())
    source_registry.register(SourceType.WEB, WebSource())
    if settings.ENABLE_PLAYWRIGHT:
        source_registry.register(SourceType.DYNAMIC_WEB, PlaywrightSource())

    logger.info(
        "Source registry initialized — %d sources available: %s",
        source_registry.count,
        ", ".join(source_registry.available_types()),
    )
