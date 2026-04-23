"""
app/services/vector_service.py
================================
In-memory FAISS index for fast cosine-similarity nearest-neighbour search.

Design
------
Uses faiss.IndexFlatIP (exact inner product) on L2-normalised vectors.
Since the vectors are unit-length, inner product equals cosine similarity:

    cosine(a, b) = a · b / (|a| · |b|) = a_norm · b_norm

The mapping from integer FAISS index positions to asset_id strings is held
in a parallel list (_index_to_asset).  Both the index and the list are
protected by threading.Lock for safe concurrent access under FastAPI's
default thread-pool request handling.

Lifecycle
---------
  Startup      → load_from_db()    bulk-loads all completed embeddings from MongoDB
  After upload → add_vector()      appends new embedding without rebuilding the index
  On /detect   → search_similar()  queries the index and filters by threshold

Similarity thresholds
---------------------
  ≥ 0.90  → "strong"   match
  0.70–0.90 → "possible" match
  < 0.70  → filtered out (not returned)

FAISS graceful fallback
------------------------
If faiss-cpu is not installed the index silently returns empty results so all
other endpoints remain functional.
"""

from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_DIM            = 2048
STRONG_MATCH_THRESHOLD   = 0.90
POSSIBLE_MATCH_THRESHOLD = 0.70

# ---------------------------------------------------------------------------
# FAISS lazy import
# ---------------------------------------------------------------------------

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False
    logger.warning(
        "faiss-cpu not found — similarity search disabled. "
        "Install with: pip install faiss-cpu"
    )


# ---------------------------------------------------------------------------
# VectorIndex class
# ---------------------------------------------------------------------------

class VectorIndex:
    """Thread-safe FAISS index + asset_id mapping."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim   = dim
        self._lock  = threading.Lock()
        self._index = None
        self._index_to_asset: list[str] = []

        if _FAISS_AVAILABLE:
            self._index = faiss.IndexFlatIP(dim)
            logger.info("FAISS IndexFlatIP initialised (dim=%d)", dim)
        else:
            logger.warning("FAISS unavailable — search will return empty results.")

    # ------------------------------------------------------------------
    # Startup: bulk load from MongoDB
    # ------------------------------------------------------------------

    def load_from_db(self) -> int:
        """
        Read all completed embeddings from MongoDB and populate the index.
        Call once from the FastAPI lifespan startup handler.

        Returns:
            Number of vectors loaded into the index.
        """
        if not _FAISS_AVAILABLE or self._index is None:
            return 0

        try:
            from app.db.mongodb import get_sync_database
            db  = get_sync_database()
            col = db["assets"]

            docs = list(col.find(
                {
                    "fingerprint": {"$exists": True, "$ne": None},
                    "status": "completed",
                },
                {"_id": 1, "fingerprint": 1},
            ))

            if not docs:
                logger.info("FAISS: no completed embeddings found in DB — index is empty.")
                return 0

            vectors   = np.array([d["fingerprint"] for d in docs], dtype=np.float32)
            asset_ids = [str(d["_id"]) for d in docs]

            with self._lock:
                self._index.reset()
                self._index_to_asset = []
                self._index.add(vectors)
                self._index_to_asset = asset_ids

            logger.info("FAISS: loaded %d embeddings from DB.", len(docs))
            return len(docs)

        except Exception as exc:
            # Do not crash startup — just log and return 0
            logger.error("FAISS load_from_db failed: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Runtime: add a single embedding
    # ------------------------------------------------------------------

    def add_vector(self, asset_id: str, embedding: list[float]) -> None:
        """
        Append one embedding to the live index without rebuilding.

        Args:
            asset_id:  MongoDB ObjectId string for the asset.
            embedding: 2048-d list of floats — must already be L2-normalised.
        """
        if not _FAISS_AVAILABLE or self._index is None:
            return

        vec_1d = np.array(embedding, dtype=np.float32)
        if vec_1d.shape[0] != self._dim:
            logger.error(
                "FAISS add rejected: dimension mismatch for asset=%s (got=%d expected=%d)",
                asset_id, vec_1d.shape[0], self._dim,
            )
            return
        vec = self._normalize_2d(vec_1d.reshape(1, -1))

        with self._lock:
            self._index.add(vec)
            self._index_to_asset.append(asset_id)

        logger.info(
            "Vector added to FAISS: %s",
            asset_id,
        )
        logger.debug(
            "FAISS: added asset %s (total vectors=%d)",
            asset_id, len(self._index_to_asset),
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        exclude_asset_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Return the top-k most similar assets to query_embedding.

        Args:
            query_embedding:   2048-d L2-normalised embedding (list of float).
            top_k:             Max number of results to return after filtering.
            exclude_asset_id:  Asset to omit from results (e.g. self-match).

        Returns:
            List of dicts ordered by similarity descending:
                {
                  "asset_id":       str,
                  "similarity":     float,     # cosine similarity 0–1
                  "match_strength": str,        # "strong" | "possible"
                }
            Only entries with similarity ≥ POSSIBLE_MATCH_THRESHOLD are returned.
        """
        if not _FAISS_AVAILABLE or self._index is None:
            logger.warning("FAISS unavailable — returning empty similarity results.")
            return []

        logger.info("Searching FAISS index")
        with self._lock:
            total = self._index.ntotal
            if total == 0:
                return []
            # search more than top_k to account for self-exclusion
            k = min(top_k + 5, total)
            query_1d = np.array(query_embedding, dtype=np.float32)
            if query_1d.shape[0] != self._dim:
                logger.error(
                    "FAISS search rejected: query dimension mismatch (got=%d expected=%d)",
                    query_1d.shape[0], self._dim,
                )
                return []
            query = self._normalize_2d(query_1d.reshape(1, -1))
            scores, indices = self._index.search(query, k)
            mapping = list(self._index_to_asset)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(mapping):
                continue
            aid = mapping[idx]
            if aid == exclude_asset_id:
                continue
            # Cosine similarity is in [-1, 1]; clip to [0, 1] for normalised vectors
            sim = float(np.clip(score, 0.0, 1.0))
            if sim < POSSIBLE_MATCH_THRESHOLD:
                continue
            results.append({
                "asset_id":       aid,
                "matched_asset_id": aid,
                "similarity":     round(sim, 4),
                "similarity_score": round(sim, 4),
                "match_strength": "strong" if sim >= STRONG_MATCH_THRESHOLD else "possible",
                "confidence": "high" if sim >= STRONG_MATCH_THRESHOLD else "medium",
            })
            if len(results) >= top_k:
                break

        logger.info("Matches found: %d", len(results))
        logger.debug(
            "FAISS search: top_k=%d | matches_above_threshold=%d",
            top_k, len(results),
        )
        return results

    @staticmethod
    def _normalize_2d(vectors: np.ndarray) -> np.ndarray:
        """L2-normalize a 2D vector batch for cosine/IP FAISS search."""
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms < 1e-9, 1.0, norms)
        return (vectors / norms).astype(np.float32)

    @property
    def total(self) -> int:
        """Number of vectors currently in the index."""
        if not _FAISS_AVAILABLE or self._index is None:
            return 0
        with self._lock:
            return self._index.ntotal


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_vector_index: Optional[VectorIndex] = None


def get_vector_index() -> VectorIndex:
    """
    Return the process-level VectorIndex singleton, creating it if needed.

    The index is populated from MongoDB at application startup via
    lifespan → get_vector_index().load_from_db().
    """
    global _vector_index
    if _vector_index is None:
        _vector_index = VectorIndex(dim=EMBEDDING_DIM)
    return _vector_index
