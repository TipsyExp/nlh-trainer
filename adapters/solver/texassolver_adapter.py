from __future__ import annotations

from typing import Any


class UnsupportedSpotError(Exception):
    """Raised when a requested node/spot cannot be solved."""


class TexasSolverAdapter:
    def __init__(self, exe_path: str) -> None:
        self.exe_path = exe_path

    def solve(self, *args: Any, **kwargs: Any) -> dict:
        raise UnsupportedSpotError("Solver integration not implemented in this slice.")
