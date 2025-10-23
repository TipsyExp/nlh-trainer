"""
Simple singleton logger accessor for the NLH trainer.

This module wraps the :class:`SQLiteLogger` defined in ``backend.database``
and provides a process‑wide singleton instance.  The logger's database
path is configured via the ``LOG_DB_PATH`` environment variable.  If
unset, a default path within ``/tmp`` is used.  Callers should use
``get_logger()`` to obtain the logger rather than instantiating
``SQLiteLogger`` directly.
"""

from __future__ import annotations

import os
from typing import Optional

from .database import SQLiteLogger

_LOGGER: Optional[SQLiteLogger] = None


def get_logger() -> SQLiteLogger:
    """Return a singleton instance of the :class:`SQLiteLogger`.

    The database file used by the logger is determined by the
    ``LOG_DB_PATH`` environment variable.  If the variable is not set,
    the logger defaults to ``/tmp/nlh_trainer.sqlite``.  This helper
    encapsulates the creation logic so that tests can override the
    environment and ensures that only one connection is opened.
    """
    global _LOGGER
    if _LOGGER is None:
        db_path = os.environ.get("LOG_DB_PATH", "/tmp/nlh_trainer.sqlite")
        _LOGGER = SQLiteLogger(db_path)
    return _LOGGER


__all__ = ["get_logger"]