"""
app/models/fingerprint_model.py
=================================
Database-layer representation of a Fingerprint document in MongoDB's
``fingerprints`` collection.

Kept deliberately decoupled from the API schema layer so storage format
and API contract can evolve independently.

Collection: fingerprints
Indexes (created at startup):
  - asset_id          (for O(1) lookup by asset)
  - user_id           (for per-user queries)
  - processing_status (for monitoring / admin)
  - (asset_id, created_at DESC) compound (for sorted latest-record lookup)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FingerprintStatus(str, Enum):
    """Processing state machine for a fingerprint record."""
    PENDING    = "pending"     # Record created; background task not yet started
    PROCESSING = "processing"  # Background task is actively running
    COMPLETED  = "completed"   # Embedding stored; FAISS index updated
    FAILED     = "failed"      # Pipeline error (see error_message for details)


class FingerprintModel(BaseModel):
    """
    Represents a single Fingerprint document in MongoDB.

    Fields
    ------
    asset_id               : str              Parent asset ObjectId string
    user_id                : str              Owner user ObjectId string
    fingerprint_type       : str              'image' | 'video'
    embedding_vector       : Optional[list]   2048-d ResNet50 feature vector
    embedding_dim          : int              Expected dimension of the vector
    model_used             : str              Model identifier string
    frame_count            : Optional[int]    Frames processed (1=image, N=video)
    processing_status      : FingerprintStatus Lifecycle state
    error_message          : Optional[str]    Set on failure
    created_at             : datetime         UTC timestamp of record creation
    completed_at           : Optional[datetime] UTC timestamp of completion
    processing_duration_ms : Optional[float]  Wall-clock pipeline duration in ms
    """

    asset_id:               str = Field(
        ..., description="ObjectId string of the parent asset."
    )
    user_id:                str = Field(
        ..., description="ObjectId string of the owning user."
    )
    fingerprint_type:       str = Field(
        ..., description="Media type of the source file: 'image' or 'video'."
    )
    embedding_vector:       Optional[List[float]] = Field(
        default=None,
        description="2048-d ResNet50 L2-normalised feature vector. Null until completed.",
    )
    embedding_dim:          int = Field(
        default=2048,
        description="Expected dimensionality of the embedding vector.",
    )
    model_used:             str = Field(
        ..., description="Full model identifier e.g. 'ResNet50-IMAGENET1K_V1-v1.0'."
    )
    frame_count:            Optional[int] = Field(
        default=None,
        description="Number of frames processed. 1 for images, N for videos.",
    )
    processing_status:      FingerprintStatus = Field(
        default=FingerprintStatus.PENDING,
        description="Current lifecycle state of the fingerprinting job.",
    )
    error_message:          Optional[str] = Field(
        default=None,
        description="Human-readable error description when status='failed'.",
    )
    created_at:             datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this fingerprint record was created.",
    )
    completed_at:           Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when fingerprinting completed (success or failure).",
    )
    processing_duration_ms: Optional[float] = Field(
        default=None,
        description="Wall-clock pipeline duration in milliseconds.",
    )

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}
