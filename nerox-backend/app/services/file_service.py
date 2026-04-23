"""
app/services/file_service.py
=============================
Stateless utilities for file validation and metadata extraction.

Responsibilities
----------------
  generate_unique_filename(original)  — UUID-based collision-safe name
  detect_file_type(filename)          — 'image' | 'video' from extension
  validate_file(upload_file)          — async; checks extension, MIME header,
                                        AND magic bytes (anti-spoofing)

What this module does NOT do
-----------------------------
Saving / deleting / URL-building for files is handled exclusively by
app.services.storage_service so the two concerns stay cleanly separated.

Security notes
--------------
* Magic-byte verification catches files that have a valid extension but a
  mismatched binary body (e.g. a PHP script renamed to photo.jpg).
* MIME-type header verification catches misconfigured clients.
* Both checks must pass; a single failure raises ValueError.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Allowed extensions → (broad_type, accepted_mime_types)
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: dict[str, tuple[str, list[str]]] = {
    ".jpg":  ("image", ["image/jpeg"]),
    ".jpeg": ("image", ["image/jpeg"]),
    ".png":  ("image", ["image/png"]),
    ".mp4":  ("video", ["video/mp4"]),
    ".mov":  ("video", ["video/quicktime", "video/mp4"]),
}
_BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".sh", ".php", ".js", ".jar", ".com", ".scr", ".msi"
}

# ---------------------------------------------------------------------------
# Magic-byte signatures for anti-spoofing verification
# ---------------------------------------------------------------------------
# Format: (offset, magic_bytes, canonical_mime)
#
# MP4 / MOV containers use ISO Base Media File Format.  The 'ftyp' box
# always sits at offset 4.  We accept any brand because the same container
# carries both MP4 and QuickTime content depending on brand bytes at offset 8.

_MAGIC: list[tuple[int, bytes, str]] = [
    (0, b"\xff\xd8\xff",         "image/jpeg"),
    (0, b"\x89PNG\r\n\x1a\n",   "image/png"),
    (4, b"ftyp",                 "video/mp4"),    # also covers .mov / QuickTime
]

_HEADER_READ_BYTES = 16   # enough for all signatures above


def _detect_mime_from_magic(header: bytes) -> str | None:
    """
    Return the detected MIME type by matching magic bytes, or None if unknown.
    """
    if len(header) >= 3 and header[0:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(header) >= 8 and header[0:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4"   # covers both mp4 and mov brands
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_unique_filename(original_filename: str) -> str:
    """
    Return a UUID4-based filename that preserves the original extension.

    Args:
        original_filename: Raw filename from the uploader.

    Returns:
        e.g. 'f47ac10b-58cc-4372-a567-0e02b2c3d479.jpg'
    """
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4()}{ext}"


def detect_file_type(filename: str) -> str:
    """
    Return 'image' or 'video' based on the file extension.

    Raises:
        ValueError: Extension is not in ALLOWED_EXTENSIONS.
    """
    ext = Path(filename).suffix.lower()
    entry = ALLOWED_EXTENSIONS.get(ext)
    if entry is None:
        raise ValueError(f"Unsupported file extension: '{ext}'")
    return entry[0]


async def validate_file(upload_file: UploadFile) -> None:
    """
    Perform three-layer file validation:

      1. Extension must be in ALLOWED_EXTENSIONS.
      2. Content-Type header (if provided) must match allowed MIME types.
      3. Magic bytes of the actual binary content must match the extension.

    The file stream is reset to byte 0 after this function returns so
    downstream code (storage_service.save_file) reads the full content.

    Args:
        upload_file: FastAPI UploadFile object.

    Raises:
        ValueError: On any validation failure (human-readable message).
    """
    original_name: str = upload_file.filename or ""
    parts = [p.lower() for p in Path(original_name).name.split(".") if p]
    if len(parts) >= 2:
        # block double-extension payloads like file.jpg.exe
        trailing = f".{parts[-1]}"
        if trailing in _BLOCKED_EXTENSIONS:
            raise ValueError("Executable or script files are not allowed.")
        if len(parts) > 2 and any(f".{p}" in _BLOCKED_EXTENSIONS for p in parts[1:]):
            raise ValueError("Suspicious multi-extension filename is not allowed.")
    ext = Path(original_name).suffix.lower()

    # ── 1. Extension check ───────────────────────────────────────────────────
    entry = ALLOWED_EXTENSIONS.get(ext)
    if entry is None:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        logger.warning("Rejected unsupported extension '%s' for file '%s'", ext, original_name)
        raise ValueError(
            f"File type '{ext}' is not supported. "
            f"Allowed formats: {allowed}."
        )

    broad_type, allowed_mimes = entry

    # ── 2. Content-Type header check (best-effort; clients can lie) ──────────
    content_type = (upload_file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in allowed_mimes:
        logger.warning(
            "Content-Type mismatch for '%s': got '%s', expected one of %s",
            original_name, content_type, allowed_mimes,
        )
        raise ValueError(
            f"Content-Type '{content_type}' does not match the expected "
            f"type for '{ext}' files ({', '.join(allowed_mimes)})."
        )

    # ── 3. Magic-byte verification (anti-spoofing) ───────────────────────────
    header = await upload_file.read(_HEADER_READ_BYTES)
    await upload_file.seek(0)  # reset so storage_service reads from the start

    if not header:
        raise ValueError("Uploaded file appears to be empty.")

    detected_mime = _detect_mime_from_magic(header)
    if detected_mime is None:
        logger.warning(
            "Magic-byte check failed for '%s' (ext=%s): unrecognised header %r",
            original_name, ext, header[:8],
        )
        raise ValueError(
            f"File content does not match a recognised '{ext}' format. "
            "Please ensure you are uploading a valid file."
        )

    # JPEG/PNG must match exactly; MP4/MOV both map to 'video/mp4' magic
    if broad_type == "image" and detected_mime != allowed_mimes[0]:
        raise ValueError(
            f"File content mismatch: extension '{ext}' suggests {allowed_mimes[0]} "
            f"but binary content indicates {detected_mime}."
        )
    if broad_type == "video" and detected_mime != "video/mp4":
        raise ValueError(
            f"File content mismatch: '{ext}' must be an ISO Base Media File "
            f"(MP4/QuickTime container)."
        )

    logger.debug(
        "Validation passed — '%s' ext=%s magic=%s", original_name, ext, detected_mime
    )
