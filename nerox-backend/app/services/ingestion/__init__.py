"""
app/services/ingestion/
========================
Modular ingestion layer for Phase 2.5 Auto-Detection Engine.

Each source module exposes a standard interface:
  async def search(query: str, max_results: int) -> List[MediaItem]

Sources:
  - youtube_source  : YouTube Data API v3 search
  - web_source      : Basic web scraper for image extraction
"""
