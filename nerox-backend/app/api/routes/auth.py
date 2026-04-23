"""
app/api/routes/auth.py
======================
Authentication endpoints for the Nerox SaaS platform.

Phase 2 upgrade: All endpoints converted to async + new endpoints added.

Endpoints
---------
POST /auth/register        — Create a new user account
POST /auth/login           — Authenticate and receive JWT access + refresh tokens
POST /auth/refresh         — Exchange a valid refresh token for a new access token
GET  /auth/me              — Return the current user's profile (legacy)
GET  /auth/profile         — Return full profile (Phase 2)
PUT  /auth/profile         — Update profile (name, company_name)
PATCH /auth/password       — Change password
POST /auth/forgot-password — Request password reset token
POST /auth/reset-password  — Reset password with token
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from jose import JWTError

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limiter import login_rate_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.db.mongodb import get_database
from app.schemas.user_schema import (
    ErrorDetail,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    PasswordChangeRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /auth/me  (legacy — kept for backward compatibility)
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    summary="Get current user profile (legacy)",
    description="Returns the authenticated user's profile (company_name, email, id).",
)
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> dict:
    return {
        "id":           str(current_user["_id"]),
        "company_name": current_user.get("company_name", ""),
        "email":        current_user.get("email", ""),
        "is_active":    current_user.get("is_active", True),
        "created_at":   current_user.get("created_at", "").isoformat() if current_user.get("created_at") else None,
    }


# ---------------------------------------------------------------------------
# GET /auth/profile  (Phase 2)
# ---------------------------------------------------------------------------

@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="Get current user profile",
    description="Returns the authenticated user's full profile including name, email, company, and creation date.",
)
async def get_profile(
    current_user: dict = Depends(get_current_user),
) -> ProfileResponse:
    return ProfileResponse(
        id=str(current_user["_id"]),
        name=current_user.get("name", current_user.get("company_name", "")),
        email=current_user.get("email", ""),
        company_name=current_user.get("company_name", ""),
        created_at=current_user.get("created_at", "").isoformat() if current_user.get("created_at") else None,
    )


# ---------------------------------------------------------------------------
# PUT /auth/profile  (Phase 2)
# ---------------------------------------------------------------------------

@router.put(
    "/profile",
    response_model=ProfileResponse,
    summary="Update user profile",
    description=(
        "Update the authenticated user's profile. "
        "Only `name` and `company_name` can be modified. "
        "Email cannot be changed through this endpoint."
    ),
)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> ProfileResponse:
    user_id = current_user["_id"]
    db = get_database()

    update_fields: dict = {"updated_at": datetime.now(timezone.utc)}

    if payload.name is not None:
        update_fields["name"] = payload.name
    if payload.company_name is not None:
        update_fields["company_name"] = payload.company_name

    if len(update_fields) == 1:
        # Only updated_at — no actual changes requested
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update. Provide at least 'name' or 'company_name'.",
        )

    await db[USERS_COLLECTION].update_one(
        {"_id": user_id},
        {"$set": update_fields},
    )

    # Fetch updated doc
    updated = await db[USERS_COLLECTION].find_one({"_id": user_id})
    logger.info("Profile updated — user_id: %s", user_id)

    return ProfileResponse(
        id=str(updated["_id"]),
        name=updated.get("name", updated.get("company_name", "")),
        email=updated.get("email", ""),
        company_name=updated.get("company_name", ""),
        created_at=updated.get("created_at", "").isoformat() if updated.get("created_at") else None,
    )


# ---------------------------------------------------------------------------
# PATCH /auth/password  (Phase 2)
# ---------------------------------------------------------------------------

@router.patch(
    "/password",
    summary="Change password",
    description=(
        "Change the authenticated user's password. "
        "Requires the current password for verification. "
        "The new password must meet complexity requirements."
    ),
    responses={
        200: {"description": "Password changed successfully"},
        400: {"description": "Current password is incorrect"},
        422: {"description": "New password doesn't meet requirements"},
    },
)
async def change_password(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    user_id = current_user["_id"]
    db = get_database()

    # Verify current password
    stored_hash = current_user.get("hashed_password", "")
    if not verify_password(payload.current_password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    # Don't allow reusing the same password
    if verify_password(payload.new_password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password.",
        )

    # Hash and update
    new_hash = hash_password(payload.new_password)
    await db[USERS_COLLECTION].update_one(
        {"_id": user_id},
        {"$set": {
            "hashed_password": new_hash,
            "token_version": int(current_user.get("token_version", 0)) + 1,
            "updated_at": datetime.now(timezone.utc),
        }},
    )

    logger.info("Password changed — user_id: %s", user_id)
    return {"message": "Password changed successfully."}


# ---------------------------------------------------------------------------
# POST /auth/forgot-password  (Phase 2)
# ---------------------------------------------------------------------------

# Reset token expiry (minutes)
RESET_TOKEN_EXPIRY_MINUTES = 30

@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password reset",
    description=(
        "Accepts an email address and generates a password reset token. "
        "For security, the response is always the same regardless of whether "
        "the email exists. The reset token is logged to console (email "
        "delivery is simulated)."
    ),
)
async def forgot_password(payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
    db = get_database()
    user_doc = await db[USERS_COLLECTION].find_one(
        {"email": payload.email.lower()},
        {"_id": 1, "email": 1, "company_name": 1},
    )

    if user_doc:
        # Generate a cryptographically secure reset token
        raw_token = secrets.token_urlsafe(48)

        # Store the hashed version (never store raw tokens)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

        await db[USERS_COLLECTION].update_one(
            {"_id": user_doc["_id"]},
            {"$set": {
                "reset_token_hash": hashed_token,
                "reset_token_expiry": expiry,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        # ── Simulate email send (console log) ──────────────────────────────
        logger.info(
            "\n"
            "╔════════════════════════════════════════════════════════════╗\n"
            "║         📧  PASSWORD RESET EMAIL (SIMULATED)             ║\n"
            "╠════════════════════════════════════════════════════════════╣\n"
            "║  To:      %s\n"
            "║  Company: %s\n"
            "║  Token:   %s\n"
            "║  Expires: %s\n"
            "║                                                          ║\n"
            "║  Reset URL:                                              ║\n"
            "║  http://localhost:5173/reset-password?token=%s            \n"
            "╚════════════════════════════════════════════════════════════╝",
            user_doc["email"],
            user_doc.get("company_name", "N/A"),
            raw_token,
            expiry.isoformat(),
            raw_token,
        )
    else:
        # Don't reveal whether the email exists — constant response
        logger.debug("Forgot-password request for non-existent email: %s", payload.email)

    # Always return the same response (no email enumeration)
    return ForgotPasswordResponse()


# ---------------------------------------------------------------------------
# POST /auth/reset-password  (Phase 2)
# ---------------------------------------------------------------------------

@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password with token",
    description=(
        "Accepts a valid reset token and new password. "
        "The token is validated against the stored hash and expiry. "
        "On success, the password is updated and the token is invalidated."
    ),
    responses={
        400: {"description": "Invalid or expired token"},
        422: {"description": "Password doesn't meet requirements"},
    },
)
async def reset_password(payload: ResetPasswordRequest) -> ResetPasswordResponse:
    db = get_database()

    # Hash the provided token to compare against stored hash
    hashed_token = hashlib.sha256(payload.token.encode()).hexdigest()

    # Find user with matching token hash that hasn't expired
    user_doc = await db[USERS_COLLECTION].find_one({
        "reset_token_hash": hashed_token,
        "reset_token_expiry": {"$gt": datetime.now(timezone.utc)},
    })

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token. Please request a new one.",
        )

    # Hash new password and update
    new_hash = hash_password(payload.new_password)
    now = datetime.now(timezone.utc)

    await db[USERS_COLLECTION].update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "hashed_password": new_hash,
                "token_version": int(user_doc.get("token_version", 0)) + 1,
                "updated_at": now,
            },
            "$unset": {
                "reset_token_hash": "",
                "reset_token_expiry": "",
            },
        },
    )

    logger.info("Password reset completed — user_id: %s", user_doc["_id"])
    return ResetPasswordResponse()


# ---------------------------------------------------------------------------
# Pre-computed dummy hash for constant-time login (user-enumeration protection)
# Generated at import time so it is always a structurally valid bcrypt hash.
# ---------------------------------------------------------------------------
_DUMMY_HASH: str = hash_password("__nerox_dummy_password_for_timing__")

# ---------------------------------------------------------------------------
# Collection name constant — change in one place if it ever needs to move
# ---------------------------------------------------------------------------
USERS_COLLECTION = "users"


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorDetail, "description": "Validation error"},
        409: {"model": ErrorDetail, "description": "E-mail already registered"},
        500: {"model": ErrorDetail, "description": "Internal server error"},
    },
    summary="Register a new user account",
    description=(
        "Creates a new user document in MongoDB.  The password is hashed with "
        "bcrypt before storage — the plain-text value is never persisted."
    ),
)
async def register_user(payload: RegisterRequest) -> RegisterResponse:
    """
    Registration flow
    -----------------
    1. Check whether the e-mail already exists (fast index lookup).
    2. Hash the password with bcrypt.
    3. Build and insert the user document.
    4. Return the new user's id and e-mail.
    """
    db = get_database()
    users = db[USERS_COLLECTION]

    # --- 1. Duplicate e-mail check ---
    existing_user = await users.find_one({"email": payload.email.lower()}, {"_id": 1})
    if existing_user:
        logger.warning("Registration attempt with existing e-mail: %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this e-mail address already exists.",
        )

    # --- 2. Hash the password ---
    hashed_pw = hash_password(payload.password)

    # --- 3. Build the user document ---
    now = datetime.now(timezone.utc)
    user_doc = {
        "name": payload.company_name.strip(),
        "company_name": payload.company_name.strip(),
        "email": payload.email.lower(),          # normalise to lowercase
        "hashed_password": hashed_pw,
        "is_active": True,
        "token_version": 0,
        "created_at": now,
        "updated_at": now,
    }

    # --- 4. Persist ---
    try:
        result = await users.insert_one(user_doc)
    except DuplicateKeyError:
        # Race-condition safeguard (unique index on email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this e-mail address already exists.",
        )
    except Exception as exc:
        logger.exception("Unexpected error during user registration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )

    logger.info("New user registered — id: %s, email: %s", result.inserted_id, payload.email)

    return RegisterResponse(
        message="User registered successfully.",
        user_id=str(result.inserted_id),
        email=payload.email,
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorDetail, "description": "Invalid credentials"},
        403: {"model": ErrorDetail, "description": "Account is inactive"},
        500: {"model": ErrorDetail, "description": "Internal server error"},
    },
    summary="Authenticate and receive JWT access + refresh tokens",
    description=(
        "Validates the user's credentials and, on success, returns a signed "
        "JWT access token and a long-lived refresh token.  Include the access "
        "token in all protected requests as: ``Authorization: Bearer <token>``"
    ),
)
async def login_user(payload: LoginRequest) -> TokenResponse:
    """
    Login flow
    ----------
    1. Fetch the user document by e-mail.
    2. Verify the supplied password against the stored bcrypt hash.
    3. Ensure the account is still active.
    4. Issue and return signed JWT access + refresh tokens.

    Security note: steps 1 and 2 return the same HTTP 401 response
    regardless of which check fails to prevent user-enumeration attacks.
    """
    db = get_database()
    users = db[USERS_COLLECTION]
    rl_key = payload.email.lower().strip()
    if not login_rate_limiter.is_allowed(rl_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait and try again.",
            headers={"Retry-After": "60"},
        )

    # --- 1. Fetch user ---
    user_doc = await users.find_one({"email": payload.email.lower()})

    # --- 2. Verify credentials (constant-time path for both failure modes) ---
    stored_hash = user_doc["hashed_password"] if user_doc else _DUMMY_HASH
    password_valid = verify_password(payload.password, stored_hash)

    if not user_doc or not password_valid:
        logger.warning("Failed login attempt for e-mail: %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid e-mail address or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 3. Account active check ---
    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact support.",
        )

    # --- 4. Issue JWTs ---
    user_id = str(user_doc["_id"])
    token_version = int(user_doc.get("token_version", 0))
    access_token = create_access_token(subject=user_id)
    refresh_token = create_refresh_token(subject=user_id, token_version=token_version)

    logger.info("Successful login — user_id: %s", user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,   # seconds
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorDetail, "description": "Invalid or expired refresh token"},
    },
    summary="Refresh an access token",
    description=(
        "Accepts a valid refresh token and returns a new access token + "
        "refresh token pair.  This allows the frontend to maintain sessions "
        "without forcing the user to re-login every 30 minutes."
    ),
)
async def refresh_access_token(payload: RefreshRequest) -> TokenResponse:
    """
    Refresh flow
    ------------
    1. Decode and validate the refresh JWT (signature + expiry + type claim).
    2. Verify the user still exists and is active.
    3. Issue a fresh access + refresh token pair.
    """
    # --- 1. Decode refresh token ---
    try:
        token_payload = decode_refresh_token(payload.refresh_token)
    except JWTError as exc:
        logger.warning("Refresh token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token payload is missing the subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 2. Verify user still exists ---
    db = get_database()
    try:
        user_doc = await db[USERS_COLLECTION].find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    token_version = int(user_doc.get("token_version", 0))
    token_version_claim = int(token_payload.get("tv", -1))
    if token_version_claim != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token was rotated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # rotate refresh token version (single-use-ish semantics)
    new_version = token_version + 1
    await db[USERS_COLLECTION].update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"token_version": new_version, "updated_at": datetime.now(timezone.utc)}},
    )

    # --- 3. Issue new token pair ---
    new_access = create_access_token(subject=user_id)
    new_refresh = create_refresh_token(subject=user_id, token_version=new_version)

    logger.info("Token refreshed — user_id: %s", user_id)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
