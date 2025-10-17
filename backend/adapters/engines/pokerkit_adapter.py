from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import hashlib, random

# --- Lightweight state objects used ONLY by the adapter acceptance/tests ---

@dataclass
class _TableSnap:
    seats: int
    sb: int
    bb: int
    ante: int
    button: int
    sb_seat: int
    bb_seat: int

@dataclass
class _PlayerSnap:
    hole_cards: List[str]

@dataclass
class _LastAction:
    seat: int
    type: str
    requested: Optional[int] = None
    committed: Optional[int] = None
    snapped: Optional[bool] = None
    bucket_label: Optional[str] = None
    allowed_buckets: Optional[List[str]] = None

@dataclass
class _GameSnap:
    table: _TableSnap
    players: List[_PlayerSnap]
    street: str
    deck_seed: Optional[str]
    last_action: Optional[_LastAction] = None  # records snapping/meta

# --- Adapter ---

class PokerKitAdapter:
    """
    Minimal adapter w/ Task-04 polish & HU preflop-open labeling fix:
      - HU preflop SB is treated as an OPEN (labels: 2.2x/2.5x/3.0x), even though to_call=BB-SB.
    """
    def __init__(self) -> None:
        # table config
        self.seats: int = 0
        self.sb: int = 0
        self.bb: int = 0
        self.ante: int = 0
        self.base_seed: Optional[str] = None

        # hand/runtime
        self.hand_id: int = 0
        self.button: int = -1
        self.sb_seat: Optional[int] = None
        self.bb_seat: Optional[int] = None
        self._street: str = "preflop"
        self._deck_seed: Optional[str] = None

        # actor & betting
        self._next_to_act: Optional[int] = None
        self._to_call_next: int = 0
        self._preflop_sb_called: bool = False
        self._last_raise_size: int = 0  # increment amount for min-raise on this street

        # cards/state
        self._players_holes: List[List[str]] = []

        # meta for tests
        self._last_action: Optional[_LastAction] = None

    # Signature must match tests: (seats, sb, bb, ante, stacks, base_seed=None)
    def start_table(
        self,
        seats: int,
        sb: int,
        bb: int,
        ante: int,
        stacks: List[int],
        base_seed: Optional[str] = None,
    ) -> None:
        if seats <= 0:
            raise ValueError("seats must be > 0")
        if len(stacks) != seats:
            raise ValueError("stacks length must equal seats")
        self.seats = seats
        self.sb = sb
        self.bb = bb
        self.ante = ante
        self.base_seed = base_seed

        # reset hand state
        self.hand_id = 0
        self.button = -1
        self.sb_seat = None
        self.bb_seat = None
        self._street = "preflop"
        self._deck_seed = None

        self._next_to_act = None
        self._to_call_next = 0
        self._preflop_sb_called = False
        self._last_raise_size = 0
        self._players_holes = []
        self._last_action = None

    # --- helpers ---

    def _seeded_rng(self, seed_text: str) -> random.Random:
        h = hashlib.sha256(seed_text.encode("utf-8")).digest()
        return random.Random(int.from_bytes(h, "big"))

    def _new_shuffled_deck(self, rng: random.Random) -> List[str]:
        ranks = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"]
        suits = ["s","h","d","c"]
        deck = [r+s for r in ranks for s in suits]
        rng.shuffle(deck)
        return deck

    def _is_hu_preflop_open(self, to_call: int, seat: int) -> bool:
        """HU preflop SB acts first; treat as an OPEN (label 2.2x/2.5x/3.0x) even though to_call==BB-SB."""
        return (
            self.seats == 2
            and self._street == "preflop"
            and seat == self.sb_seat
            and to_call == max(0, self.bb - self.sb)
        )

    def _allowed_buckets_data(self, to_call: int, seat: int) -> List[Dict[str, Any]]:
        """
        Returns buckets as dicts: {"label": str, "target": int}
        - HU preflop SB (open): 2.2x/2.5x/3x (total bet) + jam  (+ "call" still available)
        - Generic open (to_call==0): 2.2x/2.5x/3x + jam
        - Facing action (to_call>0): call, and raises {to_call + k*last_raise_size} with k in {2.5, 3.0}, + jam
        """
        buckets: List[Dict[str, Any]] = []

        # call is always present when to_call > 0
        if to_call > 0:
            buckets.append({"label": "call", "target": to_call})

        if self._is_hu_preflop_open(to_call, seat) or (to_call == 0 and self._street == "preflop"):
            # OPEN labels
            for mult in (2.2, 2.5, 3.0):
                target = int(round(mult * self.bb))
                buckets.append({"label": f"{mult:.1f}x", "target": max(target, self.bb)})
        else:
            # Facing action labels
            if to_call > 0:
                base = max(self._last_raise_size, self.bb)
                for mult in (2.5, 3.0):
                    target = to_call + int(round(mult * base))
                    buckets.append({"label": f"{mult:.1f}xR", "target": target})

        # Top of tree
        buckets.append({"label": "jam", "target": 10**12})
        buckets.sort(key=lambda b: b["target"])
        return buckets

    def _snap_to_bucket(self, requested_total: int, to_call: int, seat: int) -> Dict[str, Any]:
        bks = self._allowed_buckets_data(to_call, seat)
        best = min(bks, key=lambda b: (abs(b["target"] - requested_total), b["target"]))
        return {
            "target": best["target"],
            "snapped": requested_total != best["target"],
            "bucket_label": best["label"],
            "allowed_buckets": [b["label"] for b in bks],
        }

    # --- hand lifecycle ---

    def start_hand(self) -> str:
        if self.seats <= 0:
            raise RuntimeError("call start_table first")

        self.hand_id += 1
        self.button = (self.button + 1) % self.seats

        self.sb_seat = self.button
        self.bb_seat = (self.button + 1) % self.seats

        self._street = "preflop"
        if self.seats == 2:
            self._next_to_act = self.sb_seat
            self._to_call_next = max(0, self.bb - self.sb)
        else:
            self._next_to_act = (self.bb_seat + 1) % self.seats
            self._to_call_next = 0

        self._preflop_sb_called = False
        self._last_raise_size = self.bb

        self._deck_seed = f"{self.base_seed}:{self.hand_id}" if self.base_seed is not None else None

        rng = self._seeded_rng(self._deck_seed or f"default:{self.hand_id}")
        deck = self._new_shuffled_deck(rng)
        self._players_holes = []
        for seat in range(self.seats):
            self._players_holes.append([deck.pop(), deck.pop()])

        self._last_action = None
        return f"H{self.hand_id}"

    # --- API ---

    def next_actor(self) -> Optional[Dict[str, Any]]:
        if self._next_to_act is None:
            return None
        to_call = int(self._to_call_next)
        seat = int(self._next_to_act)
        buckets = self._allowed_buckets_data(to_call, seat)
        return {
            "seat": seat,
            "to_call": to_call,
            "allowed_buckets": [b["label"] for b in buckets],
        }

    def apply_action(self, seat: int, action: str, amount: Optional[int] = None) -> None:
        if seat != self._next_to_act:
            return

        action_l = (action or "").lower().strip()
        to_call = int(self._to_call_next)

        if action_l == "check":
            if to_call == 0:
                if self.seats == 2 and self._street == "preflop" and seat == self.bb_seat and self._preflop_sb_called:
                    self._street = "flop"
                    self._next_to_act = self.bb_seat
                    self._to_call_next = 0
                    self._last_raise_size = 0
                else:
                    self._next_to_act = self.sb_seat if seat == self.bb_seat else self.bb_seat
                    self._to_call_next = 0
            else:
                raise ValueError("illegal check facing to_call")
            self._last_action = _LastAction(seat=seat, type="check")
            return

        if action_l == "call":
            if to_call <= 0:
                return self.apply_action(seat, "check")
            if self.seats == 2 and self._street == "preflop" and seat == self.sb_seat:
                self._preflop_sb_called = True
                self._next_to_act = self.bb_seat
                self._to_call_next = 0
                self._last_action = _LastAction(seat=seat, type="call", committed=to_call)
                return
            self._next_to_act = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._to_call_next = 0
            self._last_action = _LastAction(seat=seat, type="call", committed=to_call)
            return

        if action_l in ("bet", "raise"):
            if amount is None or not isinstance(amount, int):
                raise ValueError("bet/raise requires integer 'amount' (total commitment)")

            snap = self._snap_to_bucket(requested_total=amount, to_call=to_call, seat=seat)
            committed = int(snap["target"])

            min_raise_inc = max(self.bb, self._last_raise_size)
            min_required = to_call + min_raise_inc if to_call > 0 else max(self.bb, committed)
            if to_call > 0 and committed < min_required:
                raise ValueError(f"min-raise not met: need ≥ {min_required}, got {committed}")

            if to_call == 0 or self._is_hu_preflop_open(to_call, seat):
                self._last_raise_size = max(committed, self.bb)
            else:
                self._last_raise_size = max(committed - to_call, self.bb)

            self._next_to_act = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._to_call_next = 0

            self._last_action = _LastAction(
                seat=seat,
                type=action_l,
                requested=amount,
                committed=committed,
                snapped=bool(snap["snapped"]),
                bucket_label=snap["bucket_label"],
                allowed_buckets=snap["allowed_buckets"],
            )
            return

        raise ValueError(f"unknown action: {action}")

    def state(self) -> _GameSnap:
        tbl = _TableSnap(
            seats=self.seats,
            sb=self.sb,
            bb=self.bb,
            ante=self.ante,
            button=int(self.button) if self.button >= 0 else -1,
            sb_seat=int(self.sb_seat) if self.sb_seat is not None else -1,
            bb_seat=int(self.bb_seat) if self.bb_seat is not None else -1,
        )
        players = [_PlayerSnap(hole_cards=hc[:]) for hc in self._players_holes]
        return _GameSnap(
            table=tbl,
            players=players,
            street=self._street,
            deck_seed=self._deck_seed,
            last_action=self._last_action,
        )

# Module-level singleton and factory
_ADAPTER: Optional[PokerKitAdapter] = None

def get_adapter() -> PokerKitAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = PokerKitAdapter()
    return _ADAPTER

__all__ = ["PokerKitAdapter", "get_adapter"]
