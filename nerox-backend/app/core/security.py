"""
app/core/security.py
====================
Centralises all cryptographic operations for the Nerox backend:

  • Password hashing / verification  (passlib + bcrypt)
  • JWT creation / decoding          (python-jose)

No FastAPI dependencies live here so this module can be unit-tested
in isolation without spinning up a full application.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# bcrypt is the industry-standard slow hashing algorithm for passwords.
# deprecated="auto" will automatically upgrade weaker hashes on next login.
# bcrypt_rounds=12 is the OWASP-recommended work factor (default is also 12,
# stated explicitly here for clarity).
# The "trapped" warning from passlib about bcrypt.__about__ is a known
# passlib/bcrypt version mismatch warning — it is harmless and suppressed below.
import warnings
warnings.filterwarnings(
    "ignore",
    message=".*error reading bcrypt version.*",
    category=UserWarning,
)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)



def hash_password(plain_password: str) -> str:
    """
    Returns the bcrypt hash of *plain_password*.

    Args:
        plain_password: The raw, user-supplied password string.

    Returns:
        A bcrypt hash string safe to store in the database.
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against its stored bcrypt hash.

    Args:
        plain_password:  The raw password provided by the user at login.
        hashed_password: The bcrypt hash retrieved from the database.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Creates a signed JWT access token.

    Args:
        subject:      The principal this token represents (e.g. the user's _id
                      as a string).  Stored in the ``sub`` claim.
        expires_delta: Override the default expiry window.  If omitted, the
                      value from settings.ACCESS_TOKEN_EXPIRE_MINUTES is used.

    Returns:
        A signed JWT string.
    """
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes and validates a JWT access token.

    Args:
        token: The raw JWT string received from the client.

    Returns:
        The decoded payload as a dictionary.

    Raises:
        jose.JWTError: If the token is invalid, expired, or tampered with.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    return payload


# ---------------------------------------------------------------------------
# Refresh token helpers
# ---------------------------------------------------------------------------

def create_refresh_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Creates a signed JWT refresh token with a long-lived expiry.

    The refresh token carries a ``type: refresh`` claim so the backend
    can distinguish it from access tokens and reject misuse.

    Args:
        subject:      The user's _id as a string.
        expires_delta: Override the default REFRESH_TOKEN_EXPIRE_DAYS.

    Returns:
        A signed JWT string intended for token renewal only.
    """
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    """
    Decodes a JWT refresh token and validates the ``type`` claim.

    Args:
        token: The raw refresh JWT string.

    Returns:
        The decoded payload dict.

    Raises:
        jose.JWTError: If the token is invalid, expired, or is not a refresh token.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    if payload.get("type") != "refresh":
        raise JWTError("Token is not a valid refresh token.")
    return payload

