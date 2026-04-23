"""
app/core/logger.py
==================
Centralised, structured logging for the Nerox backend.

Usage
-----
    from app.core.logger import get_logger
    logger = get_logger(__name__)

    logger.info("File uploaded: %s by user %s", filename, user_id)
    logger.warning("Validation failed: %s", detail)
    logger.error("DB write failed: %s", exc)

Format
------
    [YYYY-MM-DD HH:MM:SS] [LEVEL   ] [module.name] MESSAGE

Design
------
A single root "nerox" logger is configured once.  All child loggers
obtained via get_logger(__name__) inherit its handler automatically,
preventing duplicate log entries even across worker reloads.
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Return a consistently configured child logger under the 'nerox' namespace.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        logging.Logger instance ready to use.
    """
    root = logging.getLogger("nerox")

    if not root.handlers:
        # stdout handler — captured by Docker, systemd, uvicorn, etc.
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False  # suppress uvicorn's root-logger duplication

    return logging.getLogger(name)
