# backend/services/equity/backends/ompeval_backend.py
"""
OMPEval equity backend (adapter).

Thin Python adapter around a native OMPEval binding. If the native module
is not importable, this backend reports itself as unavailable so the
EquityService can skip it.

Expected native binding: exposes `calc_equity(players, board, dead, iters, exact, threads, timeout_ms, stderr_target) -> dict`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, cast

import importlib

from ..base import Card, EquityResult, PlayerSpec


def _load_native() -> tuple[Optional[Any], str]:
    """
    Try to import a native OMPEval binding through the unified shim.

    The shim normalizes import names across historical packages such as
    ``ompeval`` and ``nlh_ompeval``.  If import fails, returns ``(None, "")``.

    Returns:
        Tuple[module or None, str]: the imported module and the name attempted.
    """
    try:
        # Import via our local shim which re-exports whichever binding is
        # available.  This avoids scattered try/except imports throughout the
        # codebase and unifies the import path under ``ompeval``.
        from .ompeval_bindings import ompeval as mod  # type: ignore

        return mod, "ompeval"
    except Exception:
        # Fall back to dynamic discovery of known module names.
        for mod_name in ("backend.native.ompeval", "ompeval"):
            try:
                mod = importlib.import_module(mod_name)
                return mod, mod_name
            except Exception:
                continue
        return None, ""


class OmpevalBackend:
    """OMPEval-backed equity engine."""

    name: str = "ompeval"
    MAX_PLAYERS: int = 6  # OMPEval typical multiway cap

    def __init__(self, *, threads: Optional[int] = None) -> None:
        self._mod, self._binding_name = _load_native()
        self._available: bool = self._mod is not None
        self._threads: Optional[int] = threads

    # ---- Capability introspection ----

    def is_available(self) -> bool:
        return self._available and hasattr(self._mod, "calc_equity")

    def supports_ranges(self) -> bool:
        return True

    def supports_exact(self) -> bool:
        return True

    # ---- Public API (must match Protocol) ----
    def calc_equity(
        self,
        players: Sequence[PlayerSpec],
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> EquityResult:
        """
        Compute equities using OMPEval.

        Raises:
            RuntimeError: backend unavailable or native call failed.
            ValueError:   invalid inputs for native layer.
        """
        if not self._available or self._mod is None:
            raise RuntimeError(
                "OMPEval backend is not available (native module not found)."
            )

        if len(players) < 2:
            raise ValueError("need at least two players")
        if len(players) > self.MAX_PLAYERS:
            raise ValueError(f"too many players (> {self.MAX_PLAYERS}) for OMPEval")

        mode = _infer_mode(players)

        native_players: List[Dict[str, Any]] = []
        for p in players:
            if (p.hand is None) == (p.range is None):
                raise ValueError(
                    "Each player must provide exactly one of `hand` or `range`."
                )
            if p.hand is not None:
                native_players.append({"hand": [str(p.hand[0]), str(p.hand[1])]})
            else:
                native_players.append({"range": str(p.range)})

        # Normalize board/dead to simple strings
        board_s = [str(c) for c in board]
        dead_s = [str(c) for c in dead]

        # Call the native function
        try:
            res: Dict[str, Any] = cast(
                Dict[str, Any],
                self._mod.calc_equity(  # type: ignore[attr-defined]
                    players=native_players,
                    board=board_s,
                    dead=dead_s,
                    iters=iters,
                    exact=bool(exact),
                    threads=self._threads,
                    timeout_ms=timeout_ms,
                    stderr_target=None,  # can be wired via config later
                ),
            )
        except Exception as e:
            raise RuntimeError(f"ompeval native error: {e}") from e

        per_player = _normalize_per_player(res.get("per_player", []))
        backend_name = str(res.get("backend") or self.name)

        return EquityResult(
            backend=backend_name,
            mode=mode,
            n_players=int(res.get("n_players", len(players))),
            board=tuple(res.get("board", board_s)),
            dead=tuple(res.get("dead", dead_s)),
            exact=bool(res.get("exact", exact)),
            iters=cast(Optional[int], res.get("iters", iters)),
            per_player=per_player,
            raw=cast(Optional[Dict[str, Any]], res.get("raw", {})),
        )


# ---- Helpers ----


def _infer_mode(players: Sequence[PlayerSpec]) -> str:
    """Return 'hands' if all players provided fixed hands, else 'ranges'."""
    all_hands = all(p.hand is not None and p.range is None for p in players)
    return "hands" if all_hands else "ranges"


def _normalize_per_player(raw_pp: Any) -> List[Dict[str, Any]]:
    """
    Translate native per-player results to the expected shape:
      [{"win": int, "tie": int, "equity": float}, ...]
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(raw_pp, list):
        return out
    for item in raw_pp:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "win": _as_int(item.get("win", 0)),
                "tie": _as_int(item.get("tie", 0)),
                "equity": _as_float(item.get("equity", 0.0)),
            }
        )
    return out


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


__all__ = ["OmpevalBackend"]
