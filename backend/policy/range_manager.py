from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any
import os
import glob
import yaml
import logging
import random

log = logging.getLogger(__name__)


@dataclass
class RangeChoice:
    action: str  # "fold" | "call" | "raise"
    size_label: Optional[str]  # e.g., "2.5x" or "3.0xR" (None for fold/call)
    source: str  # "chart" | "fallback"


class RangeManager:
    """
    Loads preflop range charts from YAML files under data/ranges/preflop/.
    Lookup is by (seat_count, position, facing_tag) -> weighted action dist.

    YAML schema (v1), minimal example:
    ---
    schema: v1
    seat_count: 2
    positions:
      SB:
        no_raise:
          raise: {"2.2x": 40, "2.5x": 40, "3.0x": 20}
          call: 0
          fold: 0
      BB:
        vs_open_2.2x:
          fold: 20
          call: 60
          raise: {"3.0xR": 20}
    """

    def __init__(self, root: str = "data/ranges/preflop") -> None:
        self.root = root
        # index: (seat_count:str) -> positions mapping
        # positions mapping: position -> facing -> weights dict
        self._charts: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        pattern = os.path.join(self.root, "*.yaml")
        for path in glob.glob(pattern):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f) or {}
            except Exception as exc:
                log.warning("Skipping %s (read error: %s)", path, exc)
                continue

            if not isinstance(doc, dict) or doc.get("schema") != "v1":
                log.warning("Skipping %s (bad or missing schema)", path)
                continue

            seat_count = str(doc.get("seat_count"))
            positions = doc.get("positions") or {}
            if not seat_count or not isinstance(positions, dict):
                log.warning("Skipping %s (missing seat_count/positions)", path)
                continue

            self._charts.setdefault(seat_count, {})
            for pos, facings in positions.items():
                if not isinstance(facings, dict):
                    continue
                self._charts[seat_count].setdefault(pos, {})
                for facing, weights in facings.items():
                    if not isinstance(weights, dict):
                        continue
                    # expected keys: fold (int), call (int), raise (dict label->int)
                    fold_w = int(weights.get("fold", 0) or 0)
                    call_w = int(weights.get("call", 0) or 0)
                    raise_w = weights.get("raise", {})
                    if not isinstance(raise_w, dict):
                        raise_w = {}
                    self._charts[seat_count][pos][facing] = {
                        "fold": fold_w,
                        "call": call_w,
                        "raise": {str(k): int(v) for k, v in raise_w.items()},
                    }
        self._loaded = True

    def lookup_distribution(
        self, seat_count: int, position: str, facing: str
    ) -> Optional[Dict[str, Any]]:
        self._load()
        sc = str(seat_count)
        return self._charts.get(sc, {}).get(position, {}).get(facing)

    def _sample_weighted(
        self, rng: random.Random, dist: Dict[str, Any]
    ) -> Tuple[str, Optional[str]]:
        """Return (action, size_label). size_label only for 'raise'."""
        # Flatten to (action,label)->weight pairs
        pairs: Dict[Tuple[str, Optional[str]], int] = {}

        # fold/call singletons
        fw = int(dist.get("fold", 0) or 0)
        cw = int(dist.get("call", 0) or 0)
        if fw > 0:
            pairs[("fold", None)] = fw
        if cw > 0:
            pairs[("call", None)] = cw

        # raises
        rmap = dist.get("raise") or {}
        if isinstance(rmap, dict):
            for label, w in rmap.items():
                w = int(w or 0)
                if w > 0:
                    pairs[("raise", str(label))] = w

        if not pairs:
            # degenerate: nothing specified -> fallback
            return ("fold", None)

        total = sum(pairs.values())
        x = rng.uniform(0, total)
        acc = 0.0
        for (act, lab), w in pairs.items():
            acc += w
            if x <= acc:
                return (act, lab)
        # fallback (shouldn't happen)
        return ("fold", None)

    # ---- Preferred modern API used by TagBot ----
    def choose_preflop(
        self,
        *,
        position: str,
        facing: str,
        stack_bb: int,
        rng: random.Random,
        seat_count: int = 2,
    ) -> RangeChoice:
        """
        Deterministically sample an action for preflop using the provided rng.
        Returns RangeChoice. stack_bb is present for future chart selection.
        """
        dist = self.lookup_distribution(seat_count, position, facing)
        if dist:
            act, lab = self._sample_weighted(rng, dist)
            return RangeChoice(action=act, size_label=lab, source="chart")

        # Safe fallback policy when chart key missing
        if facing == "no_raise":
            return RangeChoice(action="fold", size_label=None, source="fallback")
        return RangeChoice(action="call", size_label=None, source="fallback")

    # ---- Back-compat API expected by some tests ----
    def choose_action(
        self,
        *,
        seat_count: int,
        position: str,
        facing: str,
        rng: Optional[random.Random] = None,
        seed: Optional[str] = None,
    ) -> RangeChoice:
        """
        Backward-compatible wrapper:
          - If rng is provided, use it.
          - Else if seed is provided, derive a deterministic rng from seed.
          - Else use a local Random() (non-deterministic).
        """
        if rng is None:
            rng = random.Random()
            if seed is not None:
                rng.seed(f"ranges:{seat_count}:{position}:{facing}:{seed}")
        # Reuse the same logic
        return self.choose_preflop(position=position, facing=facing, stack_bb=100, rng=rng, seat_count=seat_count)


# --- module singleton ---
_MANAGER: Optional[RangeManager] = None


def get_manager() -> RangeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = RangeManager()
    return _MANAGER
