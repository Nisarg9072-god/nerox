"""
app/core/dependencies.py
=========================
FastAPI dependency functions shared across multiple routers.

``get_current_user``
    Extracts and validates the JWT Bearer token from the Authorization header,
    then returns the authenticated user document from MongoDB.
    Inject with: ``current_user: dict = Depends(get_current_user)``
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from bson import ObjectId

from app.core.security import decode_access_token
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

# HTTPBearer enforces the presence of an "Authorization: Bearer <token>" header.
# auto_error=True (default) returns 403 automatically if the header is missing.
_bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> dict:
    """
    FastAPI dependency — validates the JWT and returns the user document.

    Flow
    ----
    1. Extract the raw token from the ``Authorization: Bearer <token>`` header.
    2. Decode and validate the JWT signature + expiry via python-jose.
    3. Pull ``sub`` (user_id) from the payload.
    4. Fetch the full user document from MongoDB to confirm the account exists
       and is still active.
    5. Return the user document dict for downstream use.

    Args:
        credentials: Injected by FastAPI from the Authorization header.

    Returns:
        The MongoDB user document (dict) for the authenticated user.

    Raises:
        HTTPException 401: Token is missing, invalid, expired, or user not found.
        HTTPException 403: Account is inactive / suspended.
    """
    token = credentials.credentials

    # --- 1 + 2. Decode JWT ---
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 3. Extract subject (user_id) ---
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing the subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 4. Fetch user from DB ---
    try:
        db = get_database()
        user_doc = db["users"].find_one({"_id": ObjectId(user_id)})
    except Exception:
        # ObjectId conversion failure or DB error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- 5. Active check ---
    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return user_doc
