# backend/logger.py
"""
Simple singleton logger accessor for the NLH trainer.

This module wraps the :class:`SQLiteLogger` defined in ``backend.database``
and provides a process-wide singleton instance. The logger's database
path is configured via the ``LOG_DB_PATH`` environment variable. If
unset, a default path within the system temp directory is used.

Use ``get_logger()`` to obtain the logger rather than instantiating
``SQLiteLogger`` directly. Tests may call ``init_logger()`` to force
reinitialization with a specific path, or ``reset_logger()`` to close
and clear the current instance.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from .database import SQLiteLogger

_LOGGER: Optional[SQLiteLogger] = None
_DB_PATH_CACHED: Optional[str] = None


def _default_db_path() -> str:
    # Cross-platform temp location (Windows/macOS/Linux)
    return os.path.join(tempfile.gettempdir(), "nlh_trainer.sqlite")


def _resolve_db_path(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    return os.environ.get("LOG_DB_PATH", _default_db_path())


def get_logger() -> SQLiteLogger:
    """Return a singleton instance of :class:`SQLiteLogger`.

    The database file used by the logger is determined by the
    ``LOG_DB_PATH`` environment variable (or a default in the system temp
    directory). If the env var changes mid-process (common during tests),
    this accessor will reinitialize the logger to point at the new path.
    """
    global _LOGGER, _DB_PATH_CACHED
    path = _resolve_db_path()
    if _LOGGER is None:
        _LOGGER = SQLiteLogger(path)
        _DB_PATH_CACHED = path
        return _LOGGER

    # If the env path changed since the last call, reinitialize.
    if _DB_PATH_CACHED != path:
        try:
            _LOGGER.close()
        except Exception:
            pass
        _LOGGER = SQLiteLogger(path)
        _DB_PATH_CACHED = path

    return _LOGGER


def init_logger(db_path: Optional[str] = None) -> SQLiteLogger:
    """Force (re)create the singleton logger with the given path.

    Useful for tests or scripts that need an isolated database, independent
    of the current LOG_DB_PATH environment variable.
    """
    global _LOGGER, _DB_PATH_CACHED
    if _LOGGER is not None:
        try:
            _LOGGER.close()
        except Exception:
            pass
    resolved = _resolve_db_path(db_path)
    _LOGGER = SQLiteLogger(resolved)
    _DB_PATH_CACHED = resolved
    return _LOGGER


def reset_logger() -> None:
    """Close and clear the current singleton logger (for tests)."""
    global _LOGGER, _DB_PATH_CACHED
    if _LOGGER is not None:
        try:
            _LOGGER.close()
        finally:
            _LOGGER = None
            _DB_PATH_CACHED = None


__all__ = ["get_logger", "init_logger", "reset_logger"]
