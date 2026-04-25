"""
app/services/storage_service.py
================================
Storage abstraction layer for the Nerox platform.

Design
------
StorageBackend is an abstract base class that defines three operations:

    save_file(upload_file, unique_filename) -> (storage_path, size_bytes)
    delete_file(storage_path)
    get_file_url(storage_path) -> url

Two concrete implementations are provided:

    LocalStorageBackend  — default; stores files under storage/uploads/
    S3StorageBackend     — stub; fill in boto3 calls when AWS S3 is needed

The factory function get_storage() reads STORAGE_TYPE from settings and
returns a module-level singleton so the backend is initialised exactly once.

Switching local → S3
---------------------
1. pip install boto3
2. Add to .env:
       STORAGE_TYPE=s3
       AWS_ACCESS_KEY_ID=...
       AWS_SECRET_ACCESS_KEY=...
       S3_BUCKET_NAME=nerox-assets
3. Implement S3StorageBackend.save_file / delete_file / get_file_url.
4. Restart the server — no API-layer changes required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import tempfile
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Directory constant (used by main.py for StaticFiles mount)
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path("storage/uploads")


def ensure_upload_dir() -> None:
    """Create the local upload directory tree if it does not already exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class StorageBackend(ABC):
    """Contract every storage provider must fulfil."""

    @abstractmethod
    async def save_file(
        self,
        upload_file: UploadFile,
        unique_filename: str,
    ) -> tuple[str, int]:
        """
        Persist the uploaded file under *unique_filename*.

        The caller is responsible for seeking upload_file back to 0 before
        calling this method if it has already been partially read.

        Args:
            upload_file:     FastAPI UploadFile object, positioned at byte 0.
            unique_filename: Collision-safe filename (UUID-based).

        Returns:
            (storage_path, size_bytes)
              storage_path — opaque path string to store in MongoDB.
              size_bytes   — total bytes written.

        Raises:
            ValueError — file exceeds the configured MAX_FILE_SIZE_MB.
            IOError    — any I/O failure during writing.
        """
        ...

    @abstractmethod
    def delete_file(self, file_path: str) -> None:
        """
        Remove a previously saved file.

        Args:
            file_path: The storage_path returned by save_file.
        """
        ...

    @abstractmethod
    def get_file_url(self, file_path: str) -> str:
        """
        Return an accessible URL for the given file_path.

        Args:
            file_path: The storage_path returned by save_file.

        Returns:
            Fully-qualified URL string clients can use to fetch the file.
        """
        ...

    @abstractmethod
    def get_processing_path(self, file_path: str) -> str:
        """
        Return a local path suitable for CPU pipelines.
        Local backend returns original path; remote backends can download a temp copy.
        """
        ...


# ---------------------------------------------------------------------------
# Local filesystem implementation
# ---------------------------------------------------------------------------


class LocalStorageBackend(StorageBackend):
    """
    Stores files on the local filesystem under *upload_dir*.
    Served to clients as /uploads/<filename> via StaticFiles.
    """

    _CHUNK_SIZE = 1024 * 1024  # 1 MB read buffer

    def __init__(self, upload_dir: Path, base_url: str) -> None:
        self.upload_dir = upload_dir
        self.base_url = base_url.rstrip("/")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorageBackend ready — dir: %s", self.upload_dir.resolve())

    async def save_file(
        self,
        upload_file: UploadFile,
        unique_filename: str,
    ) -> tuple[str, int]:
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        dest_path = self.upload_dir / unique_filename
        total_bytes = 0

        try:
            with dest_path.open("wb") as fh:
                while True:
                    chunk = await upload_file.read(self._CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        fh.close()
                        dest_path.unlink(missing_ok=True)
                        raise ValueError(
                            f"File exceeds the maximum allowed size of "
                            f"{settings.MAX_FILE_SIZE_MB} MB."
                        )
                    fh.write(chunk)

        except ValueError:
            raise
        except OSError as exc:
            dest_path.unlink(missing_ok=True)
            raise IOError(f"Failed to write file to disk: {exc}") from exc

        logger.debug(
            "Saved %s — %d bytes → %s", unique_filename, total_bytes, dest_path
        )
        return str(dest_path.resolve()), total_bytes

    def delete_file(self, file_path: str) -> None:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info("Deleted file: %s", file_path)
        else:
            logger.warning("delete_file: path not found — %s", file_path)

    def get_file_url(self, file_path: str) -> str:
        filename = Path(file_path).name
        return f"{self.base_url}/uploads/{filename}"

    def get_processing_path(self, file_path: str) -> str:
        return file_path


# ---------------------------------------------------------------------------
# AWS S3 stub — implement when ready
# ---------------------------------------------------------------------------


class S3StorageBackend(StorageBackend):
    """
    AWS S3 storage backend (not yet implemented).

    To activate:
        1. pip install boto3
        2. Set STORAGE_TYPE=s3 and AWS credentials in .env
        3. Implement the three methods below.
    """

    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME
        self.endpoint = settings.S3_ENDPOINT_URL or None
        self.public_base = settings.S3_PUBLIC_BASE_URL.rstrip("/") if settings.S3_PUBLIC_BASE_URL else ""
        if not self.bucket:
            raise RuntimeError("S3_BUCKET_NAME is required when STORAGE_TYPE=s3")
        try:
            import boto3  # type: ignore
            self._client = boto3.client(
                "s3",
                region_name=settings.S3_REGION,
                endpoint_url=self.endpoint,
                aws_access_key_id=settings.AWS_ACCESS_KEY or None,
                aws_secret_access_key=settings.AWS_SECRET_KEY or None,
            )
        except Exception as exc:
            raise RuntimeError(f"S3 backend init failed: {exc}") from exc

    async def save_file(
        self, upload_file: UploadFile, unique_filename: str
    ) -> tuple[str, int]:
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        data = await upload_file.read()
        if len(data) > max_bytes:
            raise ValueError(f"File exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB.")
        self.upload_file_to_s3(unique_filename, data, upload_file.content_type or "application/octet-stream")
        logger.info("Uploaded to S3: %s", unique_filename)
        if settings.STORAGE_MODE.lower() == "hybrid":
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            local_path = UPLOAD_DIR / unique_filename
            local_path.write_bytes(data)
            return str(local_path.resolve()), len(data)
        return unique_filename, len(data)

    def upload_file_to_s3(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def delete_file(self, file_path: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=file_path)

    def get_file_url(self, file_path: str) -> str:
        # Backward compatibility for legacy local files in hybrid mode.
        if Path(file_path).exists() and settings.STORAGE_MODE.lower() != "hybrid":
            filename = Path(file_path).name
            return f"{settings.BASE_URL.rstrip('/')}/uploads/{filename}"
        key = Path(file_path).name if Path(file_path).exists() else file_path
        if self.public_base:
            return f"{self.public_base}/{key}"
        if self.endpoint:
            return f"{self.endpoint.rstrip('/')}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.{settings.S3_REGION}.amazonaws.com/{key}"

    def generate_signed_url(self, key: str, expires_sec: int = 900) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_sec,
        )

    def get_processing_path(self, file_path: str) -> str:
        # Legacy local fallback for hybrid mode.
        if Path(file_path).exists():
            return file_path
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file_path).suffix or ".bin")
        tmp.close()
        self._client.download_file(self.bucket, file_path, tmp.name)
        return tmp.name


# ---------------------------------------------------------------------------
# Factory — module-level singleton
# ---------------------------------------------------------------------------

_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """
    Return the configured storage backend singleton.

    Reads STORAGE_TYPE from settings:
        'local'  → LocalStorageBackend  (default)
        's3'     → S3StorageBackend     (stub — implement before using)

    Any unknown value falls back to 'local' with a warning.
    """
    global _storage
    if _storage is None:
        stype = (getattr(settings, "STORAGE_MODE", "") or getattr(settings, "STORAGE_TYPE", "local")).lower()

        if stype in {"s3", "hybrid"}:
            logger.info("Initialising S3StorageBackend")
            _storage = S3StorageBackend()
        else:
            if stype != "local":
                logger.warning(
                    "Unknown STORAGE_TYPE='%s' — falling back to 'local'.", stype
                )
            _storage = LocalStorageBackend(
                upload_dir=UPLOAD_DIR,
                base_url=getattr(settings, "BASE_URL", "http://localhost:8000"),
            )

    return _storage
