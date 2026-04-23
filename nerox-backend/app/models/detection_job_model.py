"""
app/models/detection_job_model.py
====================================
MongoDB schema definition for the `detection_jobs` collection.

Phase 2.5: Auto-Detection Engine — Job tracking model.

Each detection job tracks an automated scan across external sources
(YouTube, web scraping, etc.) and records progress, matches, and errors.

Statuses:
  pending   → Job created, waiting for worker pickup
  running   → Actively scanning sources + comparing embeddings
  completed → Finished scanning; results stored
  failed    → Unrecoverable error after all retries

Sources:
  youtube   → YouTube Data API search
  web       → Web scraper (Playwright-based image extraction)
  upload    → Manual file upload (legacy, for compatibility)
  api       → External API ingestion
"""

from __future__ import annotations

DETECTION_JOBS_COL = "detection_jobs"

# Default field structure for a detection_job document.
# Use this as a reference when inserting new jobs.
DETECTION_JOB_FIELDS = {
    "user_id":        str,      # ObjectId string of the job owner
    "status":         str,      # pending | running | completed | failed
    "source":         str,      # youtube | web | upload | api
    "query":          str,      # Search keyword or URL used to find content
    "asset_ids":      list,     # List of user's asset_id strings to compare against
    "total_scanned":  int,      # Count of external media items processed
    "matches_found":  int,      # Count of similarity matches above threshold
    "results":        list,     # List of match result dicts
    "started_at":     None,     # datetime | None
    "completed_at":   None,     # datetime | None
    "error":          None,     # str | None (error message if failed)
    "created_at":     None,     # datetime (always set on insert)
}
