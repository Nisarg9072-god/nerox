"""
app/models/user_model.py
========================
Defines the internal (database-layer) representation of a User document
as stored in MongoDB.

Why a separate model from the schema?
--------------------------------------
Pydantic *schemas* describe the shape of HTTP request/response payloads.
*Models* describe the canonical shape of persisted documents.  Keeping them
separate means we can evolve the API contract independently of the storage
format and avoid accidentally leaking internal fields (e.g. hashed_password)
to API consumers.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserModel(BaseModel):
    """
    Represents a User document as it is stored in the MongoDB ``users``
    collection.

    Fields
    ------
    company_name : str
        The name of the company the user represents.
    email : str
        Unique, validated e-mail address used as the login identifier.
    hashed_password : str
        bcrypt-hashed password — **never** the plain-text value.
    is_active : bool
        Soft-delete / account suspension flag.  Defaults to True.
    created_at : datetime
        UTC timestamp set automatically at document creation.
    updated_at : datetime
        UTC timestamp updated on every write.
    """

    company_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description="Legal or trading name of the company.",
    )
    email: EmailStr = Field(
        ...,
        description="Primary contact and login e-mail address.",
    )
    hashed_password: str = Field(
        ...,
        description="bcrypt hash of the user's password.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this account is allowed to authenticate.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC datetime when the document was first created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC datetime of the last modification.",
    )

    class Config:
        # Allows the model to accept ObjectId values from MongoDB
        # transparently when used with `**document` unpacking.
        arbitrary_types_allowed = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}
