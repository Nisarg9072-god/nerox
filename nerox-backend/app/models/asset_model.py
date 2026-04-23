"""
app/models/asset_model.py
=========================
Internal database-layer representation of an Asset document
as stored in MongoDB's ``assets`` collection.

Kept deliberately separate from API schemas so we can evolve
storage format independently of the API contract.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """High-level media category inferred from MIME type."""
    IMAGE = "image"
    VIDEO = "video"


class AssetStatus(str, Enum):
    """Lifecycle state of an uploaded asset."""
    UPLOADED   = "uploaded"    # Stored on disk; fingerprinting queued
    PROCESSING = "processing"  # AI fingerprinting in progress
    COMPLETED  = "completed"   # Fully processed, embedding stored, in FAISS index
    FAILED     = "failed"      # Fingerprinting failed (check logs)


class AssetModel(BaseModel):
    """
    Represents an Asset document in MongoDB.

    Fields
    ------
    user_id           : str  — ObjectId string of the owning user
    filename          : str  — UUID-based filename on disk
    original_filename : str  — Original filename as supplied by the uploader
    file_type         : FileType  — "image" or "video"
    file_path         : str  — Absolute path to the stored file
    file_size         : int  — Size in bytes
    status            : AssetStatus  — Current lifecycle state
    fingerprint       : Optional[str]  — AI-generated hash (null until processed)
    created_at        : datetime  — UTC timestamp of upload
    """

    user_id: str = Field(
        ...,
        description="ObjectId string of the user who uploaded this asset.",
    )
    filename: str = Field(
        ...,
        description="UUID-based filename stored on disk.",
    )
    original_filename: str = Field(
        ...,
        description="Original filename as submitted by the client.",
    )
    file_type: FileType = Field(
        ...,
        description="Broad media category: 'image' or 'video'.",
    )
    file_path: str = Field(
        ...,
        description="Absolute file-system path to the stored file.",
    )
    file_size: int = Field(
        ...,
        ge=1,
        description="File size in bytes.",
    )
    status: AssetStatus = Field(
        default=AssetStatus.PROCESSING,
        description="Current processing state of the asset.",
    )
    fingerprint: Optional[list] = Field(
        default=None,
        description="2048-d ResNet50 feature vector. Null until fingerprinting completes.",
    )
    processed_at: Optional[datetime] = Field(
        default=None,
        description="UTC datetime when fingerprinting completed.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC datetime when the asset was first uploaded.",
    )

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}
