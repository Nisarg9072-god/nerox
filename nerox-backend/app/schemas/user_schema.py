"""
app/schemas/user_schema.py
===========================
Pydantic v2 schemas that define the shape of HTTP request payloads and
response bodies for all user-related endpoints.

These schemas are intentionally decoupled from UserModel (the DB layer) so
that:
  • We never accidentally expose hashed_password in API responses.
  • Request validation rules can differ from storage constraints.
  • The API contract can evolve independently of the database schema.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """
    Payload expected by ``POST /auth/register``.
    """

    company_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        examples=["Acme Corp"],
        description="Legal or trading name of the registering company.",
    )
    email: EmailStr = Field(
        ...,
        examples=["admin@acmecorp.io"],
        description="Must be a valid e-mail address. Used as the login identifier.",
    )
    password: str = Field(
        ...,
        min_length=8,
        examples=["Str0ng!Pass"],
        description="Plain-text password supplied by the user. Minimum 8 characters.",
    )

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """
        Enforce a minimal password policy:
          • At least one uppercase letter
          • At least one digit
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v

    @field_validator("company_name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class RegisterResponse(BaseModel):
    """
    Returned by ``POST /auth/register`` on success.
    """

    message: str = Field(
        default="User registered successfully.",
        description="Human-readable status message.",
    )
    user_id: str = Field(
        ...,
        description="MongoDB ObjectId of the newly created user document.",
    )
    email: EmailStr = Field(
        ...,
        description="Echo of the registered e-mail address.",
    )
    organization_id: Optional[str] = Field(
        default=None,
        description="Organization assigned at signup.",
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """
    Payload expected by ``POST /auth/login``.
    """

    email: EmailStr = Field(
        ...,
        examples=["admin@acmecorp.io"],
        description="Registered e-mail address.",
    )
    password: str = Field(
        ...,
        examples=["Str0ng!Pass"],
        description="Plain-text password to verify against the stored hash.",
    )


class TokenResponse(BaseModel):
    """
    Returned by ``POST /auth/login`` on successful authentication.
    Follows the OAuth 2.0 Bearer Token response structure for
    maximum ecosystem compatibility.
    """

    access_token: str = Field(
        ...,
        description="Signed JWT access token. Include in Authorization: Bearer <token>.",
    )
    refresh_token: str = Field(
        ...,
        description="Long-lived JWT refresh token. Use with POST /auth/refresh to get a new access token.",
    )
    token_type: str = Field(
        default="bearer",
        description="Always 'bearer'.",
    )
    expires_in: int = Field(
        ...,
        description="Token validity in seconds.",
    )


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

class RefreshRequest(BaseModel):
    """
    Payload expected by ``POST /auth/refresh``.
    """

    refresh_token: str = Field(
        ...,
        description="The refresh token received from login.",
    )


# ---------------------------------------------------------------------------
# Profile (Phase 2)
# ---------------------------------------------------------------------------

class ProfileResponse(BaseModel):
    """
    Returned by ``GET /auth/profile``.
    """
    id: str = Field(..., description="User ID (MongoDB ObjectId).")
    name: str = Field(default="", description="Display name of the user.")
    email: EmailStr = Field(..., description="E-mail address.")
    company_name: str = Field(default="", description="Company name.")
    created_at: Optional[str] = Field(None, description="Account creation timestamp (ISO 8601).")
    organization_id: Optional[str] = Field(None, description="Current organization ID.")
    role: str = Field(default="owner", description="Role in organization: owner/admin/member.")
    organization_plan: Optional[str] = Field(default="free", description="Current organization plan.")


class ProfileUpdateRequest(BaseModel):
    """
    Payload for ``PUT /auth/profile``.
    Email cannot be changed through this endpoint.
    """
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=120,
        description="Display name.",
    )
    company_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=120,
        description="Company name.",
    )

    @field_validator("name", "company_name", mode="before")
    @classmethod
    def strip_and_sanitize(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            # Basic HTML tag stripping
            import re
            v = re.sub(r"<[^>]+>", "", v)
        return v


# ---------------------------------------------------------------------------
# Password Change (Phase 2)
# ---------------------------------------------------------------------------

class PasswordChangeRequest(BaseModel):
    """
    Payload for ``PATCH /auth/password``.
    """
    current_password: str = Field(
        ...,
        description="Current password for verification.",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password. Must meet complexity requirements.",
    )

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in v):
            raise ValueError("Password must contain at least one special character.")
        return v


# ---------------------------------------------------------------------------
# Forgot / Reset Password (Phase 2)
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    """
    Payload for ``POST /auth/forgot-password``.
    """
    email: EmailStr = Field(
        ...,
        examples=["admin@acmecorp.io"],
        description="Registered e-mail address.",
    )


class ForgotPasswordResponse(BaseModel):
    """
    Returned by ``POST /auth/forgot-password``.
    Always returns success to prevent email enumeration.
    """
    message: str = Field(
        default="If this email is registered, a password reset link has been sent.",
        description="Status message.",
    )


class ResetPasswordRequest(BaseModel):
    """
    Payload for ``POST /auth/reset-password``.
    """
    token: str = Field(
        ...,
        description="Password reset token received via email.",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password. Must meet complexity requirements.",
    )

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in v):
            raise ValueError("Password must contain at least one special character.")
        return v


class ResetPasswordResponse(BaseModel):
    """
    Returned by ``POST /auth/reset-password``.
    """
    message: str = Field(
        default="Password has been reset successfully. You can now log in.",
        description="Status message.",
    )


# ---------------------------------------------------------------------------
# Shared / utility
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """
    Standard error envelope returned for 4xx / 5xx responses.
    """

    detail: str = Field(..., description="Human-readable error description.")
