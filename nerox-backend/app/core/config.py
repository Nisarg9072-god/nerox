"""
app/core/config.py
==================
Loads all environment variables via python-dotenv and exposes them
through a validated Pydantic Settings object.  Import `settings`
anywhere in the app to access configuration — never read os.environ
directly in business logic.

Environment variables (all loaded from .env)
--------------------------------------------
  MONGO_URI                  MongoDB connection string
  DB_NAME                    Target database name
  SECRET_KEY                 JWT signing secret (≥ 32 chars)
  ALGORITHM                  JWT algorithm (default: HS256)
  ACCESS_TOKEN_EXPIRE_MINUTES  Token TTL in minutes (default: 30)
  STORAGE_TYPE               'local' or 's3'  (default: local)
  MAX_FILE_SIZE_MB           Upload ceiling in megabytes (default: 50)
  BASE_URL                   Public base URL for file links
  YOUTUBE_API_KEY            YouTube Data API v3 key (Phase 2.5)
  AUTO_SCAN_INTERVAL_MIN     Scheduler interval in minutes (default: 60)
  AUTO_SCAN_MAX_ITEMS        Max media per job (default: 30)
  AUTO_SCAN_SIMILARITY_MIN   Minimum cosine similarity (default: 0.70)
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

# Load .env **before** the Settings class is instantiated so that
# environment variables are available to Pydantic.
load_dotenv()


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    # ------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------
    MONGO_URI: str
    DB_NAME: str

    # ------------------------------------------------------------------
    # JWT
    # ------------------------------------------------------------------
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    STORAGE_TYPE: str = "local"       # 'local' | 's3'
    MAX_FILE_SIZE_MB: int = 50        # Maximum upload size in megabytes
    BASE_URL: str = "http://localhost:8000"  # Public base URL (for file URLs)

    # ------------------------------------------------------------------
    # Phase 2.5: Auto-Detection Engine
    # ------------------------------------------------------------------
    YOUTUBE_API_KEY: str = ""                # YouTube Data API v3 key
    AUTO_SCAN_INTERVAL_MIN: int = 60         # Scheduler tick interval (minutes)
    AUTO_SCAN_MAX_ITEMS: int = 30            # Max media items per scan job
    AUTO_SCAN_SIMILARITY_MIN: float = 0.70   # Cosine similarity floor
    AUTO_SCAN_TIMEOUT_SEC: int = 600         # Hard timeout per job (10 min)
    AUTO_SCAN_REQUEST_DELAY: float = 1.5     # Delay between external requests (sec)
    AUTO_DETECT_MAX_WORKERS: int = 4         # ThreadPool workers for auto-detect jobs
    AUTO_DETECT_MAX_CONCURRENT_JOBS: int = 4 # Max jobs running in parallel
    ENABLE_PLAYWRIGHT: bool = True
    PLAYWRIGHT_TIMEOUT: int = 30000
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_MAX_IMAGES_PER_PAGE: int = 30
    PLAYWRIGHT_MAX_SCROLL_DEPTH: int = 6
    PLAYWRIGHT_MIN_IMAGE_SIDE_PX: int = 200
    REDIS_URL: str = "redis://localhost:6379"
    RQ_QUEUE_NAME: str = "nerox_jobs"
    MAX_JOB_RETRIES: int = 3
    RATE_LIMIT_REDIS_PREFIX: str = "nerox:rate_limit"

    # S3 / R2 (Phase 2.8 production-ready abstraction)
    S3_BUCKET_NAME: str = ""
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""
    S3_PUBLIC_BASE_URL: str = ""

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for security."
            )
        return v

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def expire_minutes_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer.")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings singleton.
    Using lru_cache ensures .env is parsed only once per process lifetime,
    which is important for performance in high-traffic environments.
    """
    return Settings()


# Convenient module-level alias used throughout the application.
settings: Settings = get_settings()
