"""
app/db/mongodb.py
=================
Manages the PyMongo client lifecycle and exposes a helper to obtain
the database instance anywhere in the application.

Design notes
------------
* A single MongoClient is created at startup and reused for every request
  (connection pooling is handled internally by PyMongo).
* `get_database()` is intentionally kept simple — it can be wrapped in a
  FastAPI `Depends()` at the route level if needed, or called directly in
  service/repository layers.
"""

import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level client — populated in connect_to_mongo()
# ---------------------------------------------------------------------------
_client: Optional[MongoClient] = None
_database: Optional[Database] = None


def connect_to_mongo() -> None:
    """
    Opens the MongoDB connection and stores the client/database references.
    Called once during FastAPI's *startup* event.

    Raises:
        ConnectionFailure: If the server is unreachable at startup.
    """
    global _client, _database

    logger.info("Connecting to MongoDB at %s …", settings.MONGO_URI)
    _client = MongoClient(
        settings.MONGO_URI,
        serverSelectionTimeoutMS=5_000,   # fail fast if Mongo is unreachable
        connectTimeoutMS=5_000,
        socketTimeoutMS=10_000,
    )

    # Force a round-trip to confirm the server is alive.
    try:
        _client.admin.command("ping")
    except ConnectionFailure as exc:
        logger.critical("MongoDB ping failed: %s", exc)
        raise

    _database = _client[settings.DB_NAME]
    logger.info("Connected to MongoDB — database: '%s'", settings.DB_NAME)


def close_mongo_connection() -> None:
    """
    Closes the MongoDB connection gracefully.
    Called once during FastAPI's *shutdown* event.
    """
    global _client
    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed.")


def get_database() -> Database:
    """
    Returns the active database instance.

    Returns:
        pymongo.database.Database bound to `settings.DB_NAME`.

    Raises:
        RuntimeError: If called before `connect_to_mongo()` has been invoked
                      (i.e. before the FastAPI startup event fires).
    """
    if _database is None:
        raise RuntimeError(
            "Database is not initialised. "
            "Ensure connect_to_mongo() is called at application startup."
        )
    return _database
