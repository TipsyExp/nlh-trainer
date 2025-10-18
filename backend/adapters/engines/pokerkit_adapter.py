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


class PokerKitAdapter:
    """
    Minimal adapter (Task-03/04) with bucket polish:
      - start_table(..., base_seed=None)
      - start_hand(): rotate BTN, set SB/BB, determine first actor, deal deterministic holes
      - next_actor(): {"seat": int, "to_call": int, "allowed_buckets": [labels]}
      - apply_action(): "check", "call", "bet", "raise" with snapping + min-raise enforcement
      - state(): object with .table.*, .players[*].hole_cards, .street, .deck_seed, .last_action

    Bucket policy (preflop):
      - Open: 2.2x / 2.5x / 3.0x (of BB)
      - 3-bet: ~3.0x IP, ~3.5x OOP (multipliers of LAST_RAISE_SIZE over call)
      - 4-bet: ~2.2x–2.5x (multipliers of LAST_RAISE_SIZE over call)
      - ≥5-bet: jam
    Postflop (simple): 33% / 66% / 100% + jam (placeholder)
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
        self._last_raise_size: int = 0     # increment amount on this street
        self._raises_this_round: int = 0   # preflop raise level: 0=open available, 1=open done, 2=3-bet done, ...

        # commitments / price
        self._committed: List[int] = []    # total committed per seat on current street
        self._current_price: int = 0       # total to be "in" on current street

        # cards/state
        self._players_holes: List[List[str]] = []

        # meta for tests
        self._last_action: Optional[_LastAction] = None

    # start_table(seats, sb, bb, ante, stacks, base_seed=None)
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
        self._raises_this_round = 0
        self._players_holes = []
        self._last_action = None

        self._committed = [0] * seats
        self._current_price = 0

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

    def _in_position_preflop_hu(self, actor_seat: int) -> bool:
        # HU: SB is in position postflop
        return actor_seat == self.sb_seat

    def _allowed_buckets_preflop(self, to_call: int, actor_seat: int) -> List[Dict[str, Any]]:
        """
        Returns dicts: {"label": str, "target": int}
        Implements:
          - Open: 2.2x/2.5x/3.0x (BB)
          - 3-bet: ~3.0x IP / ~3.5x OOP (of last_raise_size) + call
          - 4-bet: ~2.2x–2.5x (of last_raise_size) + call
          - ≥5-bet: jam (+call)
        """
        bks: List[Dict[str, Any]] = []
        if to_call > 0:
            bks.append({"label": "call", "target": to_call})

        if to_call == 0 and self._raises_this_round == 0:
            # Open
            for mult in (2.2, 2.5, 3.0):
                target = int(round(mult * self.bb))
                bks.append({"label": f"{mult:.1f}x", "target": max(target, self.bb)})
        elif to_call > 0 and self._raises_this_round == 1:
            # Facing open -> 3-bet stage
            ip = self._in_position_preflop_hu(actor_seat) if self.seats == 2 else False
            mult = 3.0 if ip else 3.5
            base = max(self._last_raise_size, self.bb)
            target = to_call + int(round(mult * base))
            bks.append({"label": f"{mult:.1f}x", "target": target})
        elif to_call > 0 and self._raises_this_round == 2:
            # Facing 3-bet -> 4-bet stage
            base = max(self._last_raise_size, self.bb)
            for mult in (2.2, 2.5):
                target = to_call + int(round(mult * base))
                bks.append({"label": f"{mult:.1f}x", "target": target})
        else:
            # ≥5-bet: jam only (+call already present if to_call>0)
            pass

        # Top of tree
        bks.append({"label": "jam", "target": 10**12})
        bks.sort(key=lambda b: b["target"])
        return bks

    def _allowed_buckets_postflop(self, to_call: int) -> List[Dict[str, Any]]:
        bks: List[Dict[str, Any]] = []
        if to_call > 0:
            bks.append({"label": "call", "target": to_call})
            # simple raises (2.5x / 3x of last raise size)
            base = max(self._last_raise_size, self.bb)
            for mult in (2.5, 3.0):
                bks.append({"label": f"{mult:.1f}x", "target": to_call + int(round(mult * base))})
        else:
            # bet 33/66/100 (we don't track pot; use BB as stand-in for ordering)
            for pct, lab in ((0.33, "33%"), (0.66, "66%"), (1.00, "100%")):
                bks.append({"label": lab, "target": max(int(round(pct * (3 * self.bb))), self.bb)})

        bks.append({"label": "jam", "target": 10**12})
        bks.sort(key=lambda b: b["target"])
        return bks

    def _allowed_buckets_data(self, to_call: int, actor_seat: int) -> List[Dict[str, Any]]:
        """
        Returns buckets as dicts: {"label": str, "target": int}

        - HU preflop, SB acting: treat as an OPEN (labels "2.2x","2.5x","3.0x")
        - Preflop open (to_call==0): 2.2x/2.5x/3x (total bet)
        - Facing action (to_call>0): include "call" and raises at {to_call + k*last_raise_size}, k∈{2.5,3.0}
        - Always include "jam"
        """
        buckets: List[Dict[str, Any]] = []

        # "call" is available whenever there is something to call
        if to_call > 0:
            buckets.append({"label": "call", "target": to_call})

        # Special-case: HU, preflop, SB (button) acting -> treat as OPEN buckets
        hu_sb_open = (
            self.seats == 2
            and self._street == "preflop"
            and actor_seat == self.sb_seat
        )

        if to_call == 0 or hu_sb_open:
            for mult in (2.2, 2.5, 3.0):
                target = int(round(mult * self.bb))
                buckets.append({"label": f"{mult:.1f}x", "target": max(target, self.bb)})
        else:
            # Facing action: raises over the current price using last_raise_size (fallback to bb)
            base = max(self._last_raise_size, self.bb)
            for mult in (2.5, 3.0):
                target = to_call + int(round(mult * base))
                buckets.append({"label": f"{mult:.1f}xR", "target": target})

        # Always include jam as a top bucket (very large sentinel)
        buckets.append({"label": "jam", "target": 10**12})

        # Sort ascending by target so snapping picks sensibly; jam remains last due to huge target
        buckets.sort(key=lambda b: b["target"])
        return buckets

    def _snap_to_bucket(self, requested_total: int, to_call: int, actor_seat: int) -> Dict[str, Any]:
        bks = self._allowed_buckets_data(to_call, actor_seat=actor_seat)
        best = min(bks, key=lambda b: (abs(b["target"] - requested_total), b["target"]))
        return {
            "target": best["target"],
            "snapped": requested_total != best["target"],
            "bucket_label": best["label"],
            "allowed_buckets": [b["label"] for b in bks],
        }

    def _rotate_to(self, seat: int) -> None:
        self._next_to_act = seat
        self._to_call_next = max(0, self._current_price - self._committed[seat])

    # --- hand lifecycle ---

    def start_hand(self) -> str:
        if self.seats <= 0:
            raise RuntimeError("call start_table first")

        self.hand_id += 1
        self.button = (self.button + 1) % self.seats

        self.sb_seat = self.button
        self.bb_seat = (self.button + 1) % self.seats

        # Reset street & betting
        self._street = "preflop"
        self._preflop_sb_called = False
        self._last_raise_size = self.bb
        self._raises_this_round = 0
        self._committed = [0] * self.seats
        self._committed[self.sb_seat] = self.sb
        self._committed[self.bb_seat] = self.bb
        self._current_price = self.bb

        # First actor + to_call
        if self.seats == 2:
            self._rotate_to(self.sb_seat)  # SB acts first preflop
        else:
            self._rotate_to((self.bb_seat + 1) % self.seats)  # UTG

        # Deterministic seed
        self._deck_seed = f"{self.base_seed}:{self.hand_id}" if self.base_seed is not None else None

        # Deal deterministic holes
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
        seat = int(self._next_to_act)
        to_call = int(self._to_call_next)
        buckets = self._allowed_buckets_data(to_call, actor_seat=self._next_to_act)
        return {
            "seat": seat,
            "to_call": to_call,
            "allowed_buckets": [b["label"] for b in buckets],
        }

    def apply_action(self, seat: int, action: str, amount: Optional[int] = None) -> None:
        if seat != self._next_to_act:
            return  # ignore out-of-turn in this minimal adapter

        action_l = (action or "").lower().strip()
        to_call = int(self._to_call_next)

        if action_l == "check":
            if to_call != 0:
                raise ValueError("illegal check facing to_call")
            # Minimal HU preflop close: if BB checks after SB called -> flop
            if self.seats == 2 and self._street == "preflop" and seat == self.bb_seat and self._preflop_sb_called:
                self._street = "flop"
                self._last_raise_size = 0
                self._raises_this_round = 0
                self._rotate_to(self.bb_seat)  # BB acts first on flop HU
            else:
                # rotate to the other seat (HU)
                self._rotate_to(self.bb_seat if seat == self.sb_seat else self.sb_seat)
            self._last_action = _LastAction(seat=seat, type="check")
            return

        if action_l == "call":
            if to_call <= 0:
                return self.apply_action(seat, "check")
            # pay to current price
            self._committed[seat] = self._current_price
            # special HU preflop tracking
            if self.seats == 2 and self._street == "preflop" and seat == self.sb_seat:
                self._preflop_sb_called = True
            # pass turn to opponent
            nxt = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._rotate_to(nxt)
            self._last_action = _LastAction(seat=seat, type="call", committed=to_call)
            return

        if action_l in ("bet", "raise"):
            if amount is None or not isinstance(amount, int):
                raise ValueError("bet/raise requires integer 'amount' (total commitment)")

            snap = self._snap_to_bucket(requested_total=amount, to_call=to_call, actor_seat=seat)
            committed_total = int(snap["target"])

            # Min-raise enforcement
            min_raise_inc = max(self.bb, self._last_raise_size)
            if to_call > 0:
                min_required = to_call + min_raise_inc
                if committed_total < min_required:
                    raise ValueError(f"min-raise not met: need ≥ {min_required}, got {committed_total}")
            else:
                # opening bet must be ≥ BB
                if committed_total < self.bb:
                    raise ValueError(f"open must be ≥ {self.bb}")

            # Update last_raise_size & raise level
            if to_call == 0:
                # Opening raise size above "0" anchor
                self._last_raise_size = max(committed_total, self.bb)
                self._raises_this_round = 1
            else:
                # Increment is new price minus prior price
                self._last_raise_size = max(committed_total - to_call, self.bb)
                self._raises_this_round = min(self._raises_this_round + 1, 99)

            # Update actor's commitment and price
            self._committed[seat] = committed_total
            self._current_price = committed_total

            # Rotate to opponent with updated to_call
            nxt = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._rotate_to(nxt)

            self._last_action = _LastAction(
                seat=seat,
                type=action_l,
                requested=amount,
                committed=committed_total,
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
