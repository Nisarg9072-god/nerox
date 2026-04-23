"""
app/db/mongodb.py
=================
Manages the Motor (async MongoDB) client lifecycle and exposes helpers to
obtain the database instance anywhere in the application.

Phase 2 upgrade: Replaced blocking PyMongo ``MongoClient`` with
Motor's ``AsyncIOMotorClient`` so all database I/O is non-blocking
and integrates cleanly with FastAPI's async event loop.

Design notes
------------
* A single AsyncIOMotorClient is created at startup and reused for every
  request (connection pooling is handled internally by Motor/PyMongo).
* ``get_database()`` returns the Motor database object — all collection
  operations must use ``await`` (e.g. ``await col.find_one(...)``).
* A synchronous ``get_sync_database()`` helper is retained for use in
  thread-pool-bound CPU workloads (fingerprinting, watermarking) where
  the calling code runs inside ``asyncio.to_thread``.
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database as SyncDatabase
from pymongo.errors import ConnectionFailure

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level clients — populated in connect_to_mongo()
# ---------------------------------------------------------------------------
_async_client: Optional[AsyncIOMotorClient] = None
_async_database: Optional[AsyncIOMotorDatabase] = None

# Sync client for thread-pool-bound operations (fingerprinting, watermarking)
_sync_client: Optional[MongoClient] = None
_sync_database: Optional[SyncDatabase] = None


async def connect_to_mongo() -> None:
    """
    Opens both async (Motor) and sync (PyMongo) MongoDB connections.
    Called once during FastAPI's lifespan startup.

    Raises:
        ConnectionFailure: If the server is unreachable at startup.
    """
    global _async_client, _async_database, _sync_client, _sync_database

    logger.info("Connecting to MongoDB at %s …", settings.MONGO_URI)

    # ── Async client (Motor) ────────────────────────────────────────────────
    _async_client = AsyncIOMotorClient(
        settings.MONGO_URI,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
        socketTimeoutMS=10_000,
    )
    # Force a round-trip to confirm the server is alive.
    try:
        await _async_client.admin.command("ping")
    except ConnectionFailure as exc:
        logger.critical("MongoDB ping failed (async): %s", exc)
        raise

    _async_database = _async_client[settings.DB_NAME]

    # ── Sync client (PyMongo — used in thread-pool workers) ─────────────────
    _sync_client = MongoClient(
        settings.MONGO_URI,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
        socketTimeoutMS=10_000,
    )
    _sync_database = _sync_client[settings.DB_NAME]

    logger.info("Connected to MongoDB — database: '%s' (async + sync)", settings.DB_NAME)


async def close_mongo_connection() -> None:
    """
    Closes both MongoDB connections gracefully.
    Called once during FastAPI's lifespan shutdown.
    """
    global _async_client, _sync_client
    if _async_client is not None:
        _async_client.close()
    if _sync_client is not None:
        _sync_client.close()
    logger.info("MongoDB connections closed.")


def get_database() -> AsyncIOMotorDatabase:
    """
    Returns the active **async** Motor database instance.

    Use this in route handlers and async service functions::

        db = get_database()
        doc = await db["collection"].find_one({"key": "value"})

    Raises:
        RuntimeError: If called before ``connect_to_mongo()`` has run.
    """
    if _async_database is None:
        raise RuntimeError(
            "Database is not initialised. "
            "Ensure connect_to_mongo() is called at application startup."
        )
    return _async_database


def get_sync_database() -> SyncDatabase:
    """
    Returns the active **synchronous** PyMongo database instance.

    Use this ONLY inside functions that run in a thread pool via
    ``asyncio.to_thread()`` — e.g. fingerprinting and watermarking
    CPU-bound pipelines where async/await cannot be used.

    Raises:
        RuntimeError: If called before ``connect_to_mongo()`` has run.
    """
    if _sync_database is None:
        raise RuntimeError(
            "Sync database is not initialised. "
            "Ensure connect_to_mongo() is called at application startup."
        )
    return _sync_database
