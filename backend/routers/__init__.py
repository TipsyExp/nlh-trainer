"""
Routers package for the FastAPI application.

Each module in this package should define an ``APIRouter`` that
encapsulates a related set of endpoints.  The main application
imports and registers these routers.
"""

from fastapi import APIRouter

__all__ = ["APIRouter"]
