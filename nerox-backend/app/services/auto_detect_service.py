"""
app/services/auto_detect_service.py
=====================================
Phase 2.5 + 2.6 — Auto Detection Engine: Core Pipeline.

Orchestrates the full automated detection workflow:
  1. Create a detection job record in MongoDB
  2. Ingest media from external sources (YouTube, web)
  3. Download and process each media item (generate embeddings)
  4. Compare embeddings against the user's FAISS index (priority-sorted)
  5. Smart match filtering (HIGH ≥0.85, MEDIUM 0.70-0.85, skip LOW)
  6. Record matches as detection + alert events
  7. Real-time WebSocket notifications for matches + progress
  8. Update the job record with results

Phase 2.6 enhancements:
  - Priority-based asset sorting (risk * 0.6 + detections * 0.3 + recency * 0.1)
  - Smart match filtering: only store MEDIUM + HIGH, alert only HIGH
  - WebSocket real-time event emissions
  - Job timeout fail-safe with reason logging
"""

from __future__ import annotations

import asyncio
import time
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
from bson import ObjectId

from app.core.config import settings
from app.core.logger import get_logger
from app.db.mongodb import get_sync_database
from app.models.detection_job_model import DETECTION_JOBS_COL

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Job creation (async — called from route handler)
# ---------------------------------------------------------------------------

async def create_detection_job(
    user_id: str,
    source:  str,
    query:   str,
    asset_ids: Optional[List[str]] = None,
) -> str:
    """
    Create a new detection job document in MongoDB.

    Called from the API route handler (async context).

    Args:
        user_id:   ObjectId string of the requesting user.
        source:    'youtube' | 'web' | 'upload' | 'api'
        query:     Search keyword or URL.
        asset_ids: Optional list of specific asset IDs to compare against.
                   If empty, all user's completed assets are used.

    Returns:
        job_id — MongoDB ObjectId string of the new job document.
    """
    from app.db.mongodb import get_database

    db = get_database()
    now = datetime.now(timezone.utc)

    doc = {
        "user_id":       user_id,
        "status":        "pending",
        "source":        source,
        "query":         query,
        "asset_ids":     asset_ids or [],
        "total_scanned": 0,
        "matches_found": 0,
        "results":       [],
        "started_at":    None,
        "completed_at":  None,
        "error":         None,
        "created_at":    now,
    }

    result = await db[DETECTION_JOBS_COL].insert_one(doc)
    job_id = str(result.inserted_id)

    logger.info(
        "Detection job created — id=%s user=%s source=%s query='%s'",
        job_id, user_id, source, query,
    )
    return job_id


# ---------------------------------------------------------------------------
# Job execution (sync — runs in TaskQueue thread pool)
# ---------------------------------------------------------------------------

def run_detection_job(job_id: str) -> None:
    """
    Execute a detection job end-to-end (synchronous, thread-pool).

    This is the main worker function dispatched by the TaskQueue.
    It orchestrates ingestion → processing → comparison → recording.

    Steps:
      1. Mark job as 'running'
      2. Resolve the user's assets and embeddings
      3. Ingest media from the configured source
      4. For each ingested item, download + generate embedding
      5. Compare against user's asset embeddings via cosine similarity
      6. Record matches as detection events + trigger alerts
      7. Mark job as 'completed' (or 'failed' on error)
    """
    db = get_sync_database()
    job_oid = ObjectId(job_id)
    t_start = time.perf_counter()

    # ── 1. Mark running ──────────────────────────────────────────────────────
    db[DETECTION_JOBS_COL].update_one(
        {"_id": job_oid},
        {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}},
    )

    job = db[DETECTION_JOBS_COL].find_one({"_id": job_oid})
    if not job:
        logger.error("Detection job %s not found in DB.", job_id)
        return

    user_id  = job["user_id"]
    source   = job["source"]
    query    = job["query"]
    asset_ids = job.get("asset_ids", [])

    logger.info(
        "Detection job RUNNING — id=%s source=%s query='%s'",
        job_id, source, query,
    )

    try:
        # Phase 2.6: Emit job progress via WebSocket
        from app.services.ws_manager import emit_job_progress, emit_job_completed, emit_job_failed

        # ── 2. Resolve user assets (Phase 2.6: priority-sorted) ──────────────
        user_assets = _get_user_assets(db, user_id, asset_ids)
        if not user_assets:
            _complete_job(db, job_oid, 0, 0, [], "No completed assets found to compare against.")
            return

        # ── 3. Ingest media from source ──────────────────────────────────────
        media_items = _run_ingestion(source, query)
        if not media_items:
            db[DETECTION_JOBS_COL].update_one(
                {"_id": job_oid},
                {"$set": {"warning": "No media found (empty results or blocked site)."}},
            )
            _complete_job(db, job_oid, 0, 0, [], None)
            return

        # Cap to configured limit
        media_items = media_items[:settings.AUTO_SCAN_MAX_ITEMS]
        logger.info(
            "Ingestion complete — job_id=%s source=%s extracted=%d",
            job_id, source, len(media_items),
        )

        # ── 4 + 5 + 6. Process & compare each item ──────────────────────────
        total_scanned = 0
        matches: List[dict] = []

        timeout_reached = False
        fingerprint_time_ms = 0.0
        similarity_time_ms = 0.0
        for item in media_items:
            # Check timeout
            elapsed = time.perf_counter() - t_start
            if elapsed > settings.AUTO_SCAN_TIMEOUT_SEC:
                logger.warning("Detection job %s timed out after %.0fs", job_id, elapsed)
                timeout_reached = True
                break

            try:
                logger.info(
                    "Auto-detect item start — job_id=%s url=%s",
                    job_id, (item.get("thumbnail_url") or item.get("url") or "")[:140],
                )
                result, timing = _process_and_compare(item, user_assets, user_id)
                total_scanned += 1
                fingerprint_time_ms += timing.get("fingerprint_time_ms", 0.0)
                similarity_time_ms += timing.get("similarity_time_ms", 0.0)

                if result:
                    matches.extend(result)

                # Update progress in real-time
                db[DETECTION_JOBS_COL].update_one(
                    {"_id": job_oid},
                    {"$set": {
                        "total_scanned": total_scanned,
                        "matches_found": len(matches),
                    }},
                )

                # Phase 2.6: Emit real-time progress via WebSocket
                emit_job_progress(
                    user_id=user_id,
                    job_id=job_id,
                    total_scanned=total_scanned,
                    matches_found=len(matches),
                )

                # Rate limit delay
                time.sleep(settings.AUTO_SCAN_REQUEST_DELAY)

            except Exception as exc:
                logger.warning(
                    "Detection job %s: failed to process item '%s': %s",
                    job_id, item.get("url", "?"), exc,
                )
                total_scanned += 1

        # ── 7. Complete job ──────────────────────────────────────────────────
        # Phase 2.6: Check if we were stopped by timeout
        elapsed_final = time.perf_counter() - t_start
        timeout_error = None
        if timeout_reached or elapsed_final > settings.AUTO_SCAN_TIMEOUT_SEC:
            timeout_error = f"Job timed out after {elapsed_final:.0f}s (limit: {settings.AUTO_SCAN_TIMEOUT_SEC}s). Partial results saved."
            logger.warning("Detection job %s — %s", job_id, timeout_error)

        _complete_job(db, job_oid, total_scanned, len(matches), matches, timeout_error)
        db[DETECTION_JOBS_COL].update_one(
            {"_id": job_oid},
            {"$set": {
                "fingerprint_time": round(fingerprint_time_ms, 2),
                "similarity_time": round(similarity_time_ms, 2),
                "total_job_time": round(elapsed_final * 1000, 2),
            }},
        )

        logger.info(
            "Detection job COMPLETED — id=%s scanned=%d matches=%d time=%.1fs",
            job_id, total_scanned, len(matches), elapsed_final,
        )

        # Phase 2.6: Emit job_completed via WebSocket
        if timeout_error:
            emit_job_failed(
                user_id=user_id,
                job_id=job_id,
                reason=timeout_error,
                total_scanned=total_scanned,
                matches_found=len(matches),
            )
        else:
            emit_job_completed(
                user_id=user_id,
                job_id=job_id,
                total_scanned=total_scanned,
                matches_found=len(matches),
                status="completed",
                top_matches=matches[:5],
                alerts=[],
            )

    except Exception as exc:
        logger.exception("Detection job FAILED — id=%s: %s", job_id, exc)
        db[DETECTION_JOBS_COL].update_one(
            {"_id": job_oid},
            {"$set": {
                "status":       "failed",
                "error":        str(exc),
                "completed_at": datetime.now(timezone.utc),
            }},
        )
        # Phase 2.6: Emit failure via WebSocket
        try:
            emit_job_failed(
                user_id=user_id,
                job_id=job_id,
                reason=str(exc),
            )
        except Exception:
            pass
        raise  # Let TaskQueue handle retry


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_user_assets(db: Any, user_id: str, asset_ids: List[str]) -> List[dict]:
    """
    Fetch the user's completed assets with embeddings.

    Phase 2.6: Returns assets sorted by priority score (highest first).
    Priority formula:
        priority = (risk_score * 0.6) + (detection_count * 0.3) + (recency * 0.1)
    This ensures high-risk, frequently detected, and recently active
    assets are compared first.
    """
    query_filter: dict = {"user_id": user_id, "status": "completed", "fingerprint": {"$ne": None}}
    if asset_ids:
        query_filter["_id"] = {"$in": [ObjectId(a) for a in asset_ids]}

    docs = list(db["assets"].find(
        query_filter,
        {"_id": 1, "fingerprint": 1, "filename": 1, "file_type": 1},
    ).limit(200))

    user_doc = {}
    try:
        user_doc = db["users"].find_one({"_id": ObjectId(user_id)}, {"plan": 1, "subscription_tier": 1, "is_premium": 1}) or {}
    except Exception:
        user_doc = {}
    plan_value = str(user_doc.get("subscription_tier") or user_doc.get("plan") or "").lower()
    premium_boost = 0.15 if user_doc.get("is_premium") or plan_value in {"premium", "enterprise", "pro"} else 0.0

    assets = []
    for d in docs:
        if not d.get("fingerprint"):
            continue

        aid = str(d["_id"])

        # Phase 2.6: Compute priority score from detection history
        det_count = db["detections"].count_documents({"asset_id": aid, "user_id": user_id})

        # Get max risk score from existing detections
        max_risk_doc = db["detections"].find_one(
            {"asset_id": aid, "user_id": user_id},
            {"risk_score": 1},
            sort=[("risk_score", -1)],
        )
        max_risk = max_risk_doc["risk_score"] if max_risk_doc else 0

        # Recency: 1.0 if detected in last 7 days, scales down
        last_det = db["detections"].find_one(
            {"asset_id": aid, "user_id": user_id},
            {"detected_at": 1},
            sort=[("detected_at", -1)],
        )
        recency = 0.0
        if last_det and last_det.get("detected_at"):
            from datetime import timedelta
            det_at = last_det["detected_at"]
            # Some existing records may have naive datetimes; treat as UTC.
            if getattr(det_at, "tzinfo", None) is None:
                det_at = det_at.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - det_at).days
            recency = max(0, 1.0 - (age_days / 30.0))  # Decay over 30 days

        priority = (max_risk / 100.0 * 0.6) + (min(det_count, 20) / 20.0 * 0.3) + (recency * 0.1) + premium_boost
        priority = min(priority, 1.0)

        # Persist priority for scheduling and analytics
        db["assets"].update_one({"_id": d["_id"]}, {"$set": {"priority_score": round(priority, 4)}})

        assets.append({
            "asset_id":       aid,
            "embedding":      d["fingerprint"],
            "filename":       d.get("filename", ""),
            "file_type":      d.get("file_type", ""),
            "priority_score": round(priority, 4),
        })

    # Sort by priority score — high-risk assets get compared first
    assets.sort(key=lambda a: a["priority_score"], reverse=True)

    logger.info(
        "Resolved %d assets for user=%s (priority-sorted)",
        len(assets), user_id,
    )
    return assets


def _run_ingestion(source: str, query: str) -> List[dict]:
    """
    Run the appropriate ingestion source synchronously.

    Since ingestion sources are async, we run them in a new event loop.
    """
    from app.services.ingestion.registry import source_registry, initialize_default_sources

    # Worker processes may execute this without FastAPI startup having run.
    # Ensure default sources are registered in this process.
    if source_registry.count == 0:
        initialize_default_sources()

    src = source_registry.get_by_name(source)
    if not src:
        logger.warning("Unknown ingestion source: '%s'", source)
        return []

    logger.info("Ingestion started — source=%s query='%s'", source, query)
    # Run async search in a new event loop (we're in a thread pool)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            items = loop.run_until_complete(
                src.search(query, max_results=settings.AUTO_SCAN_MAX_ITEMS)
            )
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Ingestion failed for source=%s query='%s': %s", source, query, exc)
        items = []

    # Fallback path: for web-like sources, try dynamic Playwright scraper when
    # standard ingestion returns nothing.
    if (not items) and source in {"web", "dynamic_web"} and settings.ENABLE_PLAYWRIGHT:
        dyn = source_registry.get_by_name("dynamic_web")
        if dyn:
            logger.info("Ingestion fallback: switching to dynamic_web for query='%s'", query)
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    items = loop.run_until_complete(
                        dyn.search(query, max_results=settings.AUTO_SCAN_MAX_ITEMS)
                    )
                finally:
                    loop.close()
            except Exception as exc:
                logger.warning("Dynamic ingestion fallback failed query='%s': %s", query, exc)
                items = []

    # Convert MediaItem dataclasses to dicts for processing
    return [
        {
            "url":             item.url,
            "title":           item.title,
            "thumbnail_url":   item.thumbnail_url,
            "source_platform": item.source_platform,
            "media_type":      item.media_type.value,
            "metadata":        item.metadata,
        }
        for item in items
    ]


def _process_and_compare(
    item: dict,
    user_assets: List[dict],
    user_id: str,
) -> tuple[List[dict], dict]:
    """
    Download a media item, generate its embedding, and compare against
    all user assets. Returns list of match dicts if similarity > threshold.
    """
    url = item.get("thumbnail_url") or item.get("url", "")
    media_type = item.get("media_type", "image")
    platform = item.get("source_platform", "unknown")

    if not url or not url.startswith("http"):
        return [], {"fingerprint_time_ms": 0.0, "similarity_time_ms": 0.0}

    # Download to temp file
    tmp_path = _download_media(url, referer=item.get("metadata", {}).get("page_url"))
    if not tmp_path:
        return [], {"fingerprint_time_ms": 0.0, "similarity_time_ms": 0.0}

    try:
        t_fp = time.perf_counter()
        # Generate embedding
        from app.services.fingerprint_service import (
            generate_embedding_for_detection,
            generate_embeddings_for_detection_variants,
        )

        # For video thumbnails, treat as image
        process_type = "image" if media_type == "image" or item.get("thumbnail_url") else "video"
        # Multi-variant embedding for images (max similarity across variants)
        if process_type == "image":
            embeddings = generate_embeddings_for_detection_variants(str(tmp_path), process_type)
        else:
            embeddings = [generate_embedding_for_detection(str(tmp_path), process_type)]

        if not embeddings or not embeddings[0]:
            return [], {"fingerprint_time_ms": 0.0, "similarity_time_ms": 0.0}
        fp_ms = (time.perf_counter() - t_fp) * 1000.0

        # Compare against each user asset
        t_sim = time.perf_counter()
        matches: List[dict] = []
        query_norms: list[np.ndarray] = []
        for emb in embeddings:
            qv = np.array(emb, dtype=np.float32)
            query_norms.append(qv / (np.linalg.norm(qv) + 1e-8))

        for asset in user_assets:
            asset_vec = np.array(asset["embedding"], dtype=np.float32)
            asset_norm = asset_vec / (np.linalg.norm(asset_vec) + 1e-8)

            # Max similarity across variants
            similarity = max(float(np.dot(qn, asset_norm)) for qn in query_norms)

            # Phase 2.6: Smart match filtering
            # HIGH_MATCH  ≥ 0.85 → Store + Alert
            # MEDIUM_MATCH 0.70–0.85 → Store only
            # LOW_MATCH   < 0.70 → Ignore completely
            if similarity < settings.AUTO_SCAN_SIMILARITY_MIN:
                continue

            # Classify match confidence
            if similarity >= float(settings.DETECT_CONFIDENCE_HIGH_MIN):
                match_confidence = "HIGH_MATCH"
                match_strength = "strong"
                should_alert = True
            elif similarity >= float(settings.DETECT_CONFIDENCE_MEDIUM_MIN):
                match_confidence = "MEDIUM_MATCH"
                match_strength = "possible"
                should_alert = False
            else:
                match_confidence = "LOW_MATCH"
                match_strength = "possible"
                should_alert = False

            match_record = {
                "asset_id":        asset["asset_id"],
                "asset_filename":  asset.get("filename", ""),
                "similarity":      round(similarity, 4),
                "match_strength":  match_strength,
                "match_confidence": match_confidence,
                "source_url":      item.get("url", ""),
                "source_title":    item.get("title", ""),
                "platform":        platform,
                "detected_at":     datetime.now(timezone.utc).isoformat(),
            }
            matches.append(match_record)

            # Create detection record (MEDIUM + HIGH stored)
            _record_detection(
                asset_id=asset["asset_id"],
                user_id=user_id,
                similarity=similarity,
                source_url=item.get("url", ""),
                platform=platform,
                should_alert=should_alert,
                confidence=match_confidence,
            )

            # Phase 2.6: Emit real-time detection_found via WebSocket
            if should_alert:
                from app.services.ws_manager import emit_detection_found
                emit_detection_found(
                    user_id=user_id,
                    asset_id=asset["asset_id"],
                    similarity=similarity,
                    source=item.get("source_platform", "unknown"),
                    source_url=item.get("url", ""),
                    platform=platform,
                    detection=match_record,
                )

        sim_ms = (time.perf_counter() - t_sim) * 1000.0
        if matches:
            top_scores = sorted([m.get("similarity", 0.0) for m in matches], reverse=True)[:5]
            logger.info(
                "auto-detect: similarity distribution (top %d) — %s",
                len(top_scores),
                [float(s) for s in top_scores],
            )
        return matches, {"fingerprint_time_ms": fp_ms, "similarity_time_ms": sim_ms}

    except Exception as exc:
        logger.warning("Failed to process media from '%s': %s", url, exc)
        return [], {"fingerprint_time_ms": 0.0, "similarity_time_ms": 0.0}

    finally:
        # Clean up temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _download_media(url: str, *, referer: str | None = None) -> Optional[Path]:
    """Download a media file to a temp location. Returns path or None."""
    def _attempt(u: str) -> Optional[bytes]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "image/*,video/*,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")

    try:
        data, content_type = _attempt(url)
        # Determine extension from content type
        ext = ".jpg"  # default
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        elif "mp4" in content_type:
            ext = ".mp4"

        # Save to temp file
        tmp = Path(tempfile.mktemp(suffix=ext, dir="storage/temp"))
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)

        logger.debug("Downloaded media: %s → %s (%d bytes)", url[:80], tmp, len(data))
        return tmp

    except Exception as exc:
        # Pinterest often blocks /originals/ without proper headers; try smaller variants.
        if "/originals/" in url:
            for variant in ("/564x/", "/474x/", "/236x/"):
                alt = url.replace("/originals/", variant)
                try:
                    data, content_type = _attempt(alt)
                    ext = ".jpg"
                    if "png" in content_type:
                        ext = ".png"
                    elif "webp" in content_type:
                        ext = ".webp"
                    tmp = Path(tempfile.mktemp(suffix=ext, dir="storage/temp"))
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    tmp.write_bytes(data)
                    logger.debug("Downloaded media (fallback): %s → %s (%d bytes)", alt[:80], tmp, len(data))
                    return tmp
                except Exception:
                    continue
        logger.warning("Failed to download '%s': %s", url[:80], exc)
        return None


def _record_detection(
    asset_id: str,
    user_id: str,
    similarity: float,
    source_url: str,
    platform: str,
    should_alert: bool = True,
    confidence: str = "MEDIUM_MATCH",
) -> None:
    """
    Create a detection record and trigger alert checks (non-fatal).

    Phase 2.6: Only alert for HIGH_MATCH confidence.
    MEDIUM_MATCH detections are stored but don't generate alerts.
    """
    try:
        from app.services.detection_service import create_detection

        create_detection(
            asset_id=asset_id,
            user_id=user_id,
            source_type="auto_scan",
            similarity_score=similarity,
            platform_name=platform,
            source_url=source_url,
            confidence_label="strong" if confidence == "HIGH_MATCH" else "medium",
            notes=f"Auto-detected via {platform} scan [{confidence}]",
        )
    except Exception as exc:
        logger.warning("Failed to record detection for asset=%s: %s", asset_id, exc)


def _complete_job(
    db: Any,
    job_oid: ObjectId,
    total_scanned: int,
    matches_found: int,
    results: List[dict],
    error: Optional[str],
) -> None:
    """Mark a detection job as completed."""
    status = "completed" if error is None else "failed"
    db[DETECTION_JOBS_COL].update_one(
        {"_id": job_oid},
        {"$set": {
            "status":        status,
            "total_scanned": total_scanned,
            "matches_found": matches_found,
            "results":       results,
            "error":         error,
            "completed_at":  datetime.now(timezone.utc),
        }},
    )
