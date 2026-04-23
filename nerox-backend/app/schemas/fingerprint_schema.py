"""
app/schemas/fingerprint_schema.py
====================================
Pydantic v2 API response schemas for fingerprint-related endpoints.

Decoupled from FingerprintModel (DB layer) so the API contract can evolve
independently of the storage format (e.g. we can add/rename fields without
a breaking API change).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FingerprintStatusResponse(BaseModel):
    """
    Returned by GET /assets/{asset_id}/fingerprint-status.

    Provides full visibility into the background fingerprinting job
    without exposing the raw 2048-d embedding vector to the client
    (use POST /detect for similarity search instead).
    """

    fingerprint_id: str = Field(
        ..., description="MongoDB ObjectId of the fingerprint record."
    )
    asset_id: str = Field(
        ..., description="MongoDB ObjectId of the parent asset."
    )
    fingerprint_type: str = Field(
        ..., description="'image' or 'video'."
    )
    processing_status: str = Field(
        ...,
        description=(
            "Current lifecycle state: "
            "'pending' → queued | "
            "'processing' → running | "
            "'completed' → ready for /detect | "
            "'failed' → see error_message"
        ),
    )
    model_used: str = Field(
        ..., description="Full model identifier (e.g. ResNet50-IMAGENET1K_V1-v1.0)."
    )
    embedding_dim: int = Field(
        ..., description="Expected dimension of the embedding vector (2048 for ResNet50)."
    )
    frame_count: Optional[int] = Field(
        default=None,
        description="Number of frames embedded. 1 for images; N for videos.",
    )
    has_embedding: bool = Field(
        ..., description="True when the embedding vector has been stored in MongoDB."
    )
    processing_duration_ms: Optional[float] = Field(
        default=None, description="Total pipeline wall-clock time in milliseconds."
    )
    error_message: Optional[str] = Field(
        default=None, description="Populated only when processing_status='failed'."
    )
    created_at: datetime = Field(
        ..., description="UTC timestamp when this fingerprint job was created."
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the job finished (success or failure).",
    )
