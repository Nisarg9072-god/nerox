"""
app/api/routes/auth.py
======================
Authentication endpoints for the Nerox SaaS platform.

Endpoints
---------
POST /auth/register  — Create a new user account
POST /auth/login     — Authenticate and receive JWT access + refresh tokens
POST /auth/refresh   — Exchange a valid refresh token for a new access token
GET  /auth/me        — Return the current user's profile

All database interactions go through PyMongo directly (no ORM).  Business
logic is kept inside each route handler for clarity; in a larger codebase
this would be extracted into a service / repository layer.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from jose import JWTError

from app.core.config import settings
from app.core.dependencies import get_current_user
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
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    summary="Get current user profile",
    description="Returns the authenticated user's profile (company_name, email, id).",
)
def get_me(
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
def register_user(payload: RegisterRequest) -> RegisterResponse:
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
    existing_user = users.find_one({"email": payload.email}, {"_id": 1})
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
        "company_name": payload.company_name.strip(),
        "email": payload.email.lower(),          # normalise to lowercase
        "hashed_password": hashed_pw,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    # --- 4. Persist ---
    try:
        result = users.insert_one(user_doc)
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
def login_user(payload: LoginRequest) -> TokenResponse:
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

    # --- 1. Fetch user ---
    user_doc = users.find_one({"email": payload.email.lower()})

    # --- 2. Verify credentials (constant-time path for both failure modes) ---
    # Even if the user doesn't exist we still call verify_password with the
    # module-level _DUMMY_HASH so response timing stays consistent and
    # prevents user-enumeration attacks via timing differences.
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
    access_token = create_access_token(subject=user_id)
    refresh_token = create_refresh_token(subject=user_id)

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
def refresh_access_token(payload: RefreshRequest) -> TokenResponse:
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
        user_doc = db[USERS_COLLECTION].find_one({"_id": ObjectId(user_id)})
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

    # --- 3. Issue new token pair ---
    new_access = create_access_token(subject=user_id)
    new_refresh = create_refresh_token(subject=user_id)

    logger.info("Token refreshed — user_id: %s", user_id)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
