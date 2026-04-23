"""
app/schemas/detect_schema.py
==============================
Request / response schemas for the POST /detect similarity-detection endpoint.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DetectionMatch(BaseModel):
    """A single asset that was found to have similar content."""

    asset_id: str = Field(
        ...,
        description="MongoDB ObjectId of the matching asset.",
    )
    matched_asset_id: str = Field(
        ...,
        description="MongoDB ObjectId of the matching asset (explicit alias).",
    )
    similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score (0 = unrelated, 1 = identical).",
    )
    match_strength: str = Field(
        ...,
        description="'strong' (≥ 0.90) or 'possible' (0.70 – 0.90).",
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Alias of similarity score for compatibility.",
    )
    confidence: str = Field(
        ...,
        description="Derived confidence label: high | medium.",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Owner user id of the matched asset.",
    )
    filename: Optional[str] = Field(
        default=None,
        description="Filename of the matched asset.",
    )


class DetectionResponse(BaseModel):
    """Response returned by POST /detect."""

    query_asset_id: Optional[str] = Field(
        default=None,
        description="Asset ID used as query source (null when a raw file was uploaded).",
    )
    total_matches: int = Field(
        ...,
        description="Number of matches found above the similarity threshold.",
    )
    matches: List[DetectionMatch] = Field(
        ...,
        description="Matches ordered by similarity score descending.",
    )
