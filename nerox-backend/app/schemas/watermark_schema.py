"""
app/schemas/watermark_schema.py
==================================
Pydantic v2 API response schemas for Phase 5 watermark endpoints.

Intentionally decoupled from WatermarkModel so the API contract and DB
storage format can evolve independently.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# GET /assets/{asset_id}/watermark-status
# ---------------------------------------------------------------------------

class VerificationLogEntry(BaseModel):
    """Single entry in the watermark audit trail."""
    verified_by_user: str
    confidence:       float
    verified_at:      str


class WatermarkStatusResponse(BaseModel):
    """
    Returned by GET /assets/{asset_id}/watermark-status.

    Exposes the full watermark job state without revealing the raw wm_token
    (token exposure would allow attackers to spoof the watermark signature).
    """

    watermark_id:       str = Field(..., description="MongoDB ObjectId of this watermark record.")
    asset_id:           str = Field(..., description="Parent asset ObjectId.")
    file_type:          str = Field(..., description="'image' or 'video'.")
    status:             str = Field(
        ...,
        description=(
            "Lifecycle state: "
            "'pending' → queued | "
            "'processing' → embedding | "
            "'completed' → watermark active | "
            "'failed' → see error_message"
        ),
    )
    watermark_method:   str   = Field(..., description="Algorithm: DCT-frequency-domain.")
    has_token:          bool  = Field(..., description="True when embedding is complete.")
    processing_duration_ms: Optional[float] = Field(
        default=None, description="Wall-clock embedding time in ms."
    )
    error_message:      Optional[str]  = Field(
        default=None, description="Failure details when status='failed'."
    )
    verification_count: int  = Field(
        default=0, description="Number of times this asset has been verified."
    )
    created_at:         datetime         = Field(..., description="UTC creation timestamp.")
    completed_at:       Optional[datetime] = Field(
        default=None, description="UTC completion timestamp."
    )
    last_verified_at:   Optional[str]  = Field(
        default=None, description="ISO timestamp of the most recent verification."
    )


# ---------------------------------------------------------------------------
# POST /watermark/verify
# ---------------------------------------------------------------------------

class OwnershipMatch(BaseModel):
    """Ownership details returned when a watermark is verified."""
    asset_id:     str  = Field(..., description="Original asset ObjectId.")
    user_id:      str  = Field(..., description="Original owner's user ObjectId.")
    watermark_id: str  = Field(..., description="Matching watermark record ObjectId.")


class VerifyResponse(BaseModel):
    """
    Returned by POST /watermark/verify.

    Provides a complete ownership trace report including confidence metrics.
    """

    verified:           bool  = Field(
        ..., description="True when token matched a completed watermark in the database."
    )
    is_verified:        bool  = Field(
        ..., description="Alias of verified for compatibility."
    )
    confidence:         float = Field(
        ..., description="DCT bit-agreement score [0.0, 1.0]. Higher = more certain."
    )
    confidence_label:   str   = Field(
        ...,
        description=(
            "Human-readable confidence tier: "
            "strong (≥0.85) | probable (0.60–0.85) | "
            "possible (0.40–0.60) | insufficient (<0.40)"
        ),
    )
    strength:           str   = Field(
        ..., description="Alias of confidence_label for compatibility."
    )
    ownership:          Optional[OwnershipMatch] = Field(
        default=None,
        description="Populated only when verified=True. Contains asset_id, user_id.",
    )
    asset_id:           Optional[str] = Field(
        default=None, description="Matched asset id when verified."
    )
    wm_token_detected:  str   = Field(
        ..., description="16-char hex of the extracted watermark token."
    )
    watermark_method:   str   = Field(
        ..., description="Algorithm used for extraction."
    )
    error:              Optional[str] = Field(
        default=None, description="Set when extraction or lookup could not complete."
    )
    message:            str = Field(
        ..., description="Human-readable verification outcome message."
    )
