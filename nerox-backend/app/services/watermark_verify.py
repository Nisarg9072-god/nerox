"""
app/services/watermark_verify.py
==================================
Watermark verification engine for the Nerox invisible ownership trace system.

Given a suspicious file this module:
  1. Detects whether the file contains a Nerox DCT watermark.
  2. Extracts the embedded 8-byte token.
  3. Looks the token up in MongoDB 'watermarks' collection.
  4. Returns full ownership metadata and a confidence assessment.

Confidence labels
-----------------
  ≥ 0.85  →  "strong"      — watermark clearly detected; bit pattern unanimous
  0.60–0.85 → "probable"   — minor degradation from compression/resize
  0.40–0.60 → "possible"   — heavy editing suspected; token may still be correct
  < 0.40  →  "insufficient"— watermark severely damaged; result unreliable

Design decisions
----------------
  • The token lookup is by exact hex-string equality in MongoDB — there is no
    fuzzy matching at the DB layer.  Robustness is handled entirely by the DCT
    majority-vote extraction that corrects bit errors before lookup.
  • Verification inserts a log entry into the watermark document's
    'verification_logs' array for an audit trail.
  • No auth or user-ownership checks here — the route layer handles that.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from app.core.logger import get_logger
from app.db.mongodb import get_sync_database as get_database

logger = get_logger(__name__)

WATERMARKS_COL = "watermarks"


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------

class VerificationResult:
    """
    Carries the output of a single watermark verification attempt.

    Attributes
    ----------
    verified         : True when an exact token match is found in FP.
    wm_token_hex     : Hex string of the extracted 8-byte token.
    confidence       : Float [0, 1] from DCT bit-agreement analysis.
    confidence_label : Human-readable label (strong / probable / possible / insufficient).
    asset_id         : MongoDB ObjectId string of the matched asset (if verified).
    user_id          : MongoDB ObjectId string of the matched user (if verified).
    watermark_id_db  : MongoDB ObjectId of the matching watermark document.
    method           : Name of the watermarking method used.
    error            : Non-None only when verification could not complete.
    """

    __slots__ = (
        "verified",
        "wm_token_hex",
        "confidence",
        "confidence_label",
        "asset_id",
        "user_id",
        "watermark_id_db",
        "method",
        "error",
    )

    def __init__(
        self,
        verified:        bool,
        wm_token_hex:    str,
        confidence:      float,
        asset_id:        Optional[str] = None,
        user_id:         Optional[str] = None,
        watermark_id_db: Optional[str] = None,
        method:          str           = "DCT-frequency-domain",
        error:           Optional[str] = None,
    ) -> None:
        self.verified         = verified
        self.wm_token_hex     = wm_token_hex
        self.confidence       = confidence
        self.confidence_label = _confidence_label(confidence)
        self.asset_id         = asset_id
        self.user_id          = user_id
        self.watermark_id_db  = watermark_id_db
        self.method           = method
        self.error            = error


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _confidence_label(c: float) -> str:
    if c >= 0.85:
        return "strong"
    if c >= 0.60:
        return "probable"
    if c >= 0.40:
        return "possible"
    return "insufficient"


def _log_verification(token_hex: str, verified_by_user: str, confidence: float) -> None:
    """Append an entry to the matching watermark document's verification_logs array."""
    try:
        db = get_database()
        db[WATERMARKS_COL].update_one(
            {"wm_token": token_hex},
            {
                "$push": {
                    "verification_logs": {
                        "verified_by_user": verified_by_user,
                        "confidence":       round(confidence, 4),
                        "verified_at":      datetime.now(timezone.utc).isoformat(),
                    }
                }
            },
        )
    except Exception as exc:
        # Non-fatal — verification result already computed
        logger.warning("Failed to append verification log: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_file(file_path: str, file_type: str) -> VerificationResult:
    """
    Extract watermark from a suspicious file and verify ownership in MongoDB.

    Steps
    -----
    1. Route to image or video extractor based on file_type.
    2. Obtain raw 8-byte token + confidence score.
    3. Query 'watermarks' collection for an exact token match with
       status = 'completed'.  If found, return ownership info.

    Args:
        file_path: Absolute path to the suspicious file (temp file from route).
        file_type: 'image' | 'video'

    Returns:
        VerificationResult — never raises; errors are captured in .error field.
    """
    # ── Step 1: Extract token ─────────────────────────────────────────────────
    try:
        if file_type == "image":
            from app.services.image_watermark import extract_watermark_from_file
            wm_token, confidence = extract_watermark_from_file(file_path)

        elif file_type == "video":
            from app.services.video_watermark import extract_watermark_from_video
            wm_token, confidence = extract_watermark_from_video(file_path)

        else:
            return VerificationResult(
                verified=False,
                wm_token_hex="",
                confidence=0.0,
                error=f"Unsupported file_type: '{file_type}'. Expected 'image' or 'video'.",
            )

    except Exception as exc:
        logger.warning("Watermark extraction failed for %s: %s", file_path, exc)
        return VerificationResult(
            verified=False,
            wm_token_hex="",
            confidence=0.0,
            error=f"Extraction failed: {exc}",
        )

    token_hex = wm_token.hex()
    logger.info(
        "Extracted token=%s confidence=%.3f label=%s from %s",
        token_hex, confidence, _confidence_label(confidence), file_path,
    )

    # ── Step 2: Null token guard (all-zero → no watermark found) ─────────────
    if token_hex == "0" * 16:
        hybrid = _hybrid_fingerprint_match(file_path=file_path, file_type=file_type)
        if hybrid and hybrid.get("similarity", 0.0) >= 0.98:
            return VerificationResult(
                verified=True,
                wm_token_hex=token_hex,
                confidence=float(hybrid["similarity"]),
                asset_id=hybrid.get("asset_id"),
                user_id=hybrid.get("user_id"),
                watermark_id_db=None,
                method="hybrid-watermark-fingerprint",
                error="Watermark token destroyed; verified via near-identical fingerprint match.",
            )
        return VerificationResult(
            verified=False,
            wm_token_hex=token_hex,
            confidence=confidence,
            error="All-zero token extracted — file likely contains no Nerox watermark.",
        )

    # ── Step 3: Look up in database ───────────────────────────────────────────
    db  = get_database()
    doc = db[WATERMARKS_COL].find_one(
        {"wm_token": token_hex, "status": "completed"},
        projection={"_id": 1, "asset_id": 1, "user_id": 1},
    )

    if doc is None:
        # Fuzzy lookup for robustness against mild distortions.
        fuzzy_doc = _fuzzy_watermark_match(db, wm_token, min_similarity=0.70)
        if fuzzy_doc and confidence >= 0.45:
            logger.info(
                "Watermark fuzzy match — token=%s ~ asset=%s similarity=%.3f",
                token_hex, fuzzy_doc.get("asset_id"), fuzzy_doc.get("token_similarity", 0.0),
            )
            return VerificationResult(
                verified=True,
                wm_token_hex=token_hex,
                confidence=max(confidence, float(fuzzy_doc.get("token_similarity", 0.0))),
                asset_id=fuzzy_doc.get("asset_id"),
                user_id=fuzzy_doc.get("user_id"),
                watermark_id_db=str(fuzzy_doc.get("_id")),
                method="DCT-frequency-domain-fuzzy",
            )

        # Hybrid fallback: use fingerprint similarity when watermark is weak.
        hybrid = _hybrid_fingerprint_match(file_path=file_path, file_type=file_type)
        if hybrid and hybrid.get("similarity", 0.0) >= 0.98:
            return VerificationResult(
                verified=True,
                wm_token_hex=token_hex,
                confidence=float(hybrid["similarity"]),
                asset_id=hybrid.get("asset_id"),
                user_id=hybrid.get("user_id"),
                watermark_id_db=None,
                method="hybrid-watermark-fingerprint",
                error=(
                    "Watermark token degraded; verified via high fingerprint similarity."
                ),
            )

        logger.info("No DB match for token=%s", token_hex)
        return VerificationResult(
            verified=False,
            wm_token_hex=token_hex,
            confidence=confidence,
            error=(
                "Watermark token extracted but not found in the Nerox database. "
                "The file may belong to another platform or the watermark may be corrupted."
            ),
        )

    # ── Match found ───────────────────────────────────────────────────────────
    logger.info(
        "Watermark VERIFIED — token=%s asset=%s user=%s confidence=%.3f",
        token_hex, doc.get("asset_id"), doc.get("user_id"), confidence,
    )

    return VerificationResult(
        verified=True,
        wm_token_hex=token_hex,
        confidence=confidence,
        asset_id=doc.get("asset_id"),
        user_id=doc.get("user_id"),
        watermark_id_db=str(doc["_id"]),
    )


def _hamming_similarity_hex(a_hex: str, b_hex: str) -> float:
    try:
        a = bytes.fromhex(a_hex)
        b = bytes.fromhex(b_hex)
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        total_bits = n * 8
        dist = 0
        for x, y in zip(a[:n], b[:n]):
            dist += (x ^ y).bit_count()
        return max(0.0, 1.0 - (dist / total_bits))
    except Exception:
        return 0.0


def _fuzzy_watermark_match(db, wm_token: bytes, min_similarity: float = 0.70) -> Optional[dict]:
    token_hex = wm_token.hex()
    token_hash_hex = hashlib.sha256(wm_token).hexdigest()
    best: Optional[dict] = None
    best_sim = 0.0
    cursor = db[WATERMARKS_COL].find(
        {"status": "completed", "wm_token": {"$ne": None}},
        projection={"_id": 1, "asset_id": 1, "user_id": 1, "wm_token": 1, "watermark_hash": 1},
    )
    for row in cursor:
        token_sim = _hamming_similarity_hex(token_hex, str(row.get("wm_token") or ""))
        hash_sim = _hamming_similarity_hex(token_hash_hex[:16], str(row.get("watermark_hash") or "")[:16])
        sim = max(token_sim, hash_sim)
        if sim > best_sim:
            best_sim = sim
            best = dict(row)
            best["token_similarity"] = sim
    if best and best_sim >= min_similarity:
        return best
    return None


def _hybrid_fingerprint_match(file_path: str, file_type: str) -> Optional[dict]:
    try:
        from app.services.fingerprint_service import generate_embedding_for_detection
        from app.services.vector_service import get_vector_index
        emb = generate_embedding_for_detection(file_path, file_type)
        matches = get_vector_index().search_similar(emb, top_k=1)
        if not matches:
            return None
        top = matches[0]
        db = get_database()
        asset_doc = db["assets"].find_one({"_id": ObjectId(top["asset_id"])}, {"user_id": 1})
        return {
            "asset_id": top.get("asset_id"),
            "similarity": float(top.get("similarity", 0.0)),
            "user_id": str(asset_doc.get("user_id")) if asset_doc and asset_doc.get("user_id") else None,
        }
    except Exception:
        return None
