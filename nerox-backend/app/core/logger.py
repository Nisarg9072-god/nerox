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

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured production logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        reserved = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process",
        }
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


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

        formatter = JsonFormatter()
        handler.setFormatter(formatter)

        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False  # suppress uvicorn's root-logger duplication

    return logging.getLogger(name)
