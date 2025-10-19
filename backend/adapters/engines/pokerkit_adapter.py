"""
Minimal PokerKit‑like engine adapter.

This module provides a very lightweight No‑Limit Hold'em engine that
supports heads‑up and multi‑player tables.  It implements a reduced
feature set sufficient for M0 testing: posting blinds, deterministic
deck shuffling based on a seed, heads‑up preflop order rules, basic
bet sizing buckets, minimum raise enforcement, and off‑tree size
snapping.  It does **not** handle side pots, showdown evaluation or
complex betting rounds.  It is intended solely as a stub for early
milestones and is not production ready.

The core class is ``PokerKitAdapter``; a module‑level ``get_adapter``
function returns a singleton instance to share state across API
handlers.  See the docstrings on individual methods for usage.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Lightweight snapshot dataclasses
#
# These dataclasses capture a minimal view of the current game state.  They
# intentionally omit much of the full game model (pot breakdown, action
# history, etc.) because the early API only needs to surface a few fields.

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
    pot_total: int = 0
    last_action: Optional[_LastAction] = None


class PokerKitAdapter:
    """A minimal poker engine for testing.

    This adapter exposes methods to configure a table (``start_table``),
    start a new hand (``start_hand``), query the next actor
    (``next_actor``), apply actions (``apply_action``), and obtain a
    lightweight snapshot of the current state (``state``).  It models a
    simple HU preflop structure with bucketised bet sizing and
    deterministic deck shuffling.
    """

    # --- Table lifecycle -----------------------------------------------------

    def __init__(self) -> None:
        # Table configuration
        self.seats: int = 0
        self.sb: int = 0
        self.bb: int = 0
        self.ante: int = 0
        self.base_seed: Optional[str] = None
        # Hand/runtime state
        self.hand_id: int = 0
        self.button: int = -1
        self.sb_seat: Optional[int] = None
        self.bb_seat: Optional[int] = None
        self._street: str = "preflop"
        self._deck_seed: Optional[str] = None
        # Actor & betting state
        self._next_to_act: Optional[int] = None
        self._to_call_next: int = 0
        self._preflop_sb_called: bool = False
        self._last_raise_size: int = 0
        self._raises_this_round: int = 0
        # Committed amounts and pricing
        self._committed: List[int] = []
        self._current_price: int = 0
        # Cards/state
        self._players_holes: List[List[str]] = []
        self._pot_total: int = 0
        # Metadata for last action
        self._last_action: Optional[_LastAction] = None

    # --- Internal helpers ----------------------------------------------------

    def _seeded_rng(self, seed_text: str) -> random.Random:
        """Create a deterministic PRNG from a text seed.

        We use SHA256 to derive a numeric seed from the provided text.
        """
        h = hashlib.sha256(seed_text.encode("utf-8")).digest()
        return random.Random(int.from_bytes(h, "big"))

    def _new_shuffled_deck(self, rng: random.Random) -> List[str]:
        """Return a new shuffled deck of 52 cards using the provided RNG."""
        ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
        suits = ["s", "h", "d", "c"]
        deck = [r + s for r in ranks for s in suits]
        rng.shuffle(deck)
        return deck

    def _in_position_preflop_hu(self, actor_seat: int) -> bool:
        """Return whether the actor is in position for HU preflop.

        In heads‑up play the small blind (button) is considered in
        position postflop.  This helper is used when selecting 3‑bet
        sizing multipliers.
        """
        return actor_seat == self.sb_seat

    def _allowed_buckets_data(self, to_call: int, actor_seat: Optional[int]) -> List[Dict[str, Any]]:
        """Compute the allowed bet/raise buckets for the current actor.

        Buckets are expressed as dicts with ``label`` and ``target`` keys.
        The target is the total amount a player must be committed to after
        the action (including any call portion).  The calling option is
        always provided when ``to_call > 0``.
        """
        buckets: List[Dict[str, Any]] = []
        # Allow calling if there is something to call
        if to_call > 0:
            buckets.append({"label": "call", "target": to_call})

        # Determine if this is an open (no bet) or a heads‑up SB open
        hu_sb_open = (
            self.seats == 2
            and self._street == "preflop"
            and actor_seat is not None
            and actor_seat == self.sb_seat
        )
        if to_call == 0 or hu_sb_open:
            # Opening raise buckets: 2.2×/2.5×/3.0× big blind
            for mult in (2.2, 2.5, 3.0):
                target = int(round(mult * self.bb))
                buckets.append({"label": f"{mult:.1f}x", "target": max(target, self.bb)})
        else:
            # Facing action: raises over the current price using last raise size
            base = max(self._last_raise_size, self.bb)
            for mult in (2.5, 3.0):
                target = to_call + int(round(mult * base))
                buckets.append({"label": f"{mult:.1f}xR", "target": target})

        # Always include jam as a sentinel bucket with a huge target
        buckets.append({"label": "jam", "target": 10**12})

        # Sort ascending by target so snapping picks the smallest option first
        buckets.sort(key=lambda b: b["target"])
        return buckets

    def _snap_to_bucket(
        self,
        requested_total: int,
        to_call: int,
        actor_seat: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Snap a requested total commitment to the nearest allowed bucket.

        The caller must supply ``requested_total`` as the player’s desired
        total commitment (including any call amount).  The returned dict
        includes the chosen ``target`` commitment, a boolean ``snapped``
        flag indicating if the input was adjusted, the ``bucket_label``
        that was chosen and the list of all bucket labels available.
        """
        buckets = self._allowed_buckets_data(to_call, actor_seat)
        # Extract jam and non‑jam targets
        jam_bucket = next((b for b in buckets if b["label"] == "jam"), None)
        nonjam = [b for b in buckets if b["label"] != "jam"]
        nonjam_targets = [b["target"] for b in nonjam]
        max_non_jam = max(nonjam_targets) if nonjam_targets else 0
        # Force jam when the request is absurdly large
        jam_floor = max(self.bb * 100, max_non_jam * 20)
        if requested_total >= jam_floor:
            if jam_bucket:
                best = jam_bucket
            else:
                # Fallback if jam bucket is missing: use largest non‑jam
                biggest_nonjam = max(nonjam, key=lambda b: b["target"], default=None)
                if biggest_nonjam is not None:
                    best = {"label": "jam", "target": biggest_nonjam["target"]}
                else:
                    best = {"label": "jam", "target": int(to_call)}
        else:
            # Select the allowed bucket with minimal distance to the request
            best = min(buckets, key=lambda b: (abs(int(b["target"]) - int(requested_total)), int(b["target"])))

        return {
            "target": int(best["target"]),
            "snapped": int(requested_total) != int(best["target"]),
            "bucket_label": best["label"],
            "allowed_buckets": [b["label"] for b in buckets],
        }

    def _rotate_to(self, seat: int) -> None:
        """Set the next actor and compute their amount to call."""
        self._next_to_act = seat
        # Amount the actor must call to match the current price
        self._to_call_next = max(0, self._current_price - self._committed[seat])

    def _compute_min_raise(self, to_call: int) -> int:
        """Compute the minimum raise target based on the current state."""
        if to_call <= 0:
            # Opening raise: must be at least the big blind or last raise size
            return max(self.bb, self._last_raise_size or self.bb)
        # Facing action: min raise = call + max(bb, last_raise_size)
        return to_call + max(self.bb, self._last_raise_size or self.bb)

    # --- Public API ---------------------------------------------------------

    def start_table(
        self,
        seats: int,
        sb: int,
        bb: int,
        ante: int,
        stacks: List[int],
        base_seed: Optional[str] = None,
    ) -> None:
        """Configure a new table with the given parameters.

        Args:
            seats: Number of seats at the table.
            sb: Small blind amount.
            bb: Big blind amount.
            ante: Ante amount (unused in M0).
            stacks: List of starting stack sizes for each seat.
            base_seed: Optional base seed used for deterministic shuffling.

        Raises:
            ValueError: If seats <= 0 or stacks length does not match seats.
        """
        if seats <= 0:
            raise ValueError("seats must be > 0")
        if len(stacks) != seats:
            raise ValueError("stacks length must equal seats")
        self.seats = seats
        self.sb = sb
        self.bb = bb
        self.ante = ante
        self.base_seed = base_seed
        # Reset per‑hand state
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
        self._committed = [0] * seats
        self._current_price = 0
        self._players_holes = []
        self._pot_total = 0
        self._last_action = None

    def start_hand(self) -> str:
        """Begin a new hand and deal deterministic hole cards.

        Returns:
            A hand identifier string (e.g. ``H1`` for the first hand).
        """
        if self.seats <= 0:
            raise RuntimeError("call start_table first")
        # Increment hand counter and rotate button
        self.hand_id += 1
        self.button = (self.button + 1) % self.seats
        # Assign blinds
        self.sb_seat = self.button
        self.bb_seat = (self.button + 1) % self.seats
        # Reset street and betting
        self._street = "preflop"
        self._preflop_sb_called = False
        self._last_raise_size = self.bb
        self._raises_this_round = 0
        # Reset commitments: post blinds
        self._committed = [0] * self.seats
        self._committed[self.sb_seat] = self.sb
        self._committed[self.bb_seat] = self.bb
        self._current_price = self.bb
        # Determine first actor: HU preflop -> SB acts first
        if self.seats == 2:
            self._rotate_to(self.sb_seat)
        else:
            # Multiway: actor after BB
            self._rotate_to((self.bb_seat + 1) % self.seats)
        # Build deterministic seed for deck
        if self.base_seed is not None:
            self._deck_seed = f"{self.base_seed}:{self.hand_id}"
        else:
            self._deck_seed = None
        # Deal hole cards deterministically
        rng = self._seeded_rng(self._deck_seed or f"default:{self.hand_id}")
        deck = self._new_shuffled_deck(rng)
        self._players_holes = []
        for _seat in range(self.seats):
            # Each player gets two cards
            self._players_holes.append([deck.pop(), deck.pop()])
        # Clear last action
        self._last_action = None
        return f"H{self.hand_id}"

    def next_actor(self) -> Optional[Dict[str, Any]]:
        """Return the next actor and their call amount, or None if no action."""
        if self._next_to_act is None:
            return None
        seat = int(self._next_to_act)
        to_call = int(self._to_call_next)
        buckets = self._allowed_buckets_data(to_call, actor_seat=self._next_to_act)
        return {
            "seat": seat,
            "to_call": to_call,
            "min_raise": int(self._compute_min_raise(to_call)),
            "allowed_buckets": [b["label"] for b in buckets],
        }

    def apply_action(self, seat: int, action: str, amount: Optional[int] = None) -> None:
        """Apply an action for a given seat.

        Args:
            seat: The acting seat index.
            action: One of "check", "call", "bet", or "raise".
            amount: When betting or raising, the total amount the player
                intends to be committed to (call + raise).  Ignored for
                check/call.

        Raises:
            ValueError: If the action is illegal (e.g., checking when facing a bet)
                or the bet/raise amount is below the minimum.
        """
        # Ignore out‑of‑turn actions
        if seat != self._next_to_act:
            return
        action_l = (action or "").lower().strip()
        to_call = int(self._to_call_next)

        # ----- Check -----
        if action_l == "check":
            if to_call != 0:
                raise ValueError("illegal check facing to_call")
            # Heads‑up preflop: if BB checks after SB has called, transition to flop
            if (
                self.seats == 2
                and self._street == "preflop"
                and seat == self.bb_seat
                and self._preflop_sb_called
            ):
                # Special case: heads‑up check behind preflop ends the hand for M0.
                # We transition to the flop street but do not offer further
                # actions; instead we clear the next actor to signal hand completion.
                self._street = "flop"
                self._last_raise_size = 0
                self._raises_this_round = 0
                self._next_to_act = None
            else:
                # Rotate to opponent
                nxt = self.bb_seat if seat == self.sb_seat else self.sb_seat
                self._rotate_to(nxt)
            # Record last action
            self._last_action = _LastAction(seat=seat, type="check")
            return

        # ----- Call -----
        if action_l == "call":
            if to_call <= 0:
                # Call without anything to call -> treat as check
                self.apply_action(seat, "check")
                return
            # Pay to match the current price
            self._committed[seat] = self._current_price
            # Track if small blind has called preflop (HU) to detect SB call -> BB check -> flop pattern
            if self.seats == 2 and self._street == "preflop" and seat == self.sb_seat:
                self._preflop_sb_called = True
            # Rotate to opponent
            nxt = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._rotate_to(nxt)
            self._last_action = _LastAction(seat=seat, type="call", committed=to_call)
            return

        # ----- Bet/Raise -----
        if action_l in ("bet", "raise"):
            if amount is None or not isinstance(amount, int):
                raise ValueError("bet/raise requires integer 'amount' (total commitment)")
            snap = self._snap_to_bucket(requested_total=amount, to_call=to_call, actor_seat=seat)
            committed_total = int(snap["target"])
            # Minimum raise enforcement
            if to_call > 0:
                min_required = to_call + max(self.bb, self._last_raise_size)
                if committed_total < min_required:
                    raise ValueError(f"min-raise not met: need ≥ {min_required}, got {committed_total}")
            else:
                # Opening bet must be at least the big blind
                if committed_total < self.bb:
                    raise ValueError(f"open must be ≥ {self.bb}")
            # Update last raise size & raise level
            if to_call == 0:
                # Opening raise size above 0 anchor
                self._last_raise_size = max(committed_total, self.bb)
                self._raises_this_round = 1
            else:
                # Raise increment is the difference from the call price
                self._last_raise_size = max(committed_total - to_call, self.bb)
                self._raises_this_round = min(self._raises_this_round + 1, 99)
            # Update actor's commitment and global price
            self._committed[seat] = committed_total
            self._current_price = committed_total
            # Rotate to opponent
            nxt = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._rotate_to(nxt)
            # Record last action
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
        """Return a lightweight snapshot of the current hand."""
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
            pot_total=int(self._pot_total),
            last_action=self._last_action,
        )


# ---------------------------------------------------------------------------
# Singleton access
#
_ADAPTER: Optional[PokerKitAdapter] = None


def get_adapter() -> PokerKitAdapter:
    """Return a singleton instance of the PokerKitAdapter."""
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = PokerKitAdapter()
    return _ADAPTER

__all__ = ["PokerKitAdapter", "get_adapter"]