# backend/adapters/engines/pokerkit_adapter.py
"""
Minimal PokerKit-like engine adapter.

This module provides a very lightweight No-Limit Hold'em engine that
supports heads-up and multi-player tables.  It implements a reduced
feature set sufficient for M0/M1 testing: posting blinds, deterministic
deck shuffling based on a seed, heads-up preflop order rules, basic
bet sizing buckets, minimum raise enforcement, off-tree size snapping,
and HU street transitions.  It is intended as a stub for early milestones.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Lightweight snapshot dataclasses


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
    # Always provide board with flop/turn/river arrays (possibly empty)
    board: Dict[str, List[str]] = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------


class PokerKitAdapter:
    # --- Class-level annotations for mypy ---
    _preflop_sb_called: bool

    """A minimal poker engine for testing."""

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
        self._last_raise_size: int = (
            0  # size of the last raise (delta to previous price)
        )
        self._raises_this_round: int = 0
        # Committed amounts and pricing (running totals)
        self._committed: List[int] = []
        self._current_price: int = 0
        # Cards/state
        self._players_holes: List[List[str]] = []
        self._deck: List[str] = []  # remaining deck (top is end for .pop())
        self._board: List[str] = []  # running community cards (0..4)
        self._pot_total: int = 0
        # Metadata for last action
        self._last_action: Optional[_LastAction] = None
        # Pot monotonicity guard (per hand)
        self._pot_guard_prev: int = 0
        self._pot_guard_hand_epoch: int = (
            0  # mirrors hand_id at time of last guard update
        )

    # --- Internal helpers ----------------------------------------------------

    def _seeded_rng(self, seed_text: str) -> random.Random:
        h = hashlib.sha256(seed_text.encode("utf-8")).digest()
        return random.Random(int.from_bytes(h, "big"))

    def _new_shuffled_deck(self, rng: random.Random) -> List[str]:
        ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
        suits = ["s", "h", "d", "c"]
        deck = [r + s for r in ranks for s in suits]
        rng.shuffle(deck)
        return deck

    def _deal_board_to_street(self) -> None:
        """Deterministically extend the board to match the current street."""
        # We don't emulate burns; just deal straight from self._deck.
        if self._street == "flop":
            if len(self._board) < 3 and len(self._deck) >= 3:
                self._board.extend(
                    [self._deck.pop(), self._deck.pop(), self._deck.pop()]
                )
        elif self._street == "turn":
            if len(self._board) < 4 and self._deck:
                self._board.append(self._deck.pop())
        elif self._street == "river":
            if len(self._board) < 5 and self._deck:
                self._board.append(self._deck.pop())

    def _opponent_of(self, seat: int) -> int:
        # HU only helper. For multiway, replace with rotation logic.
        if self.seats != 2:
            raise RuntimeError("Only HU rotation implemented in stub adapter")
        return self.bb_seat if seat == self.sb_seat else self.sb_seat  # type: ignore[return-value]

    def _is_true_sb_open_pf(self, actor_seat: Optional[int]) -> bool:
        """True HU SB open = first preflop decision at blind price."""
        return (
            self.seats == 2
            and self._street == "preflop"
            and actor_seat is not None
            and actor_seat == self.sb_seat
            and self._current_price == self.bb  # no price increase yet
            and self._raises_this_round == 0
            and self._last_action is None
        )

    def _allowed_buckets_data(
        self, to_call: int, actor_seat: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Compute allowed bet/raise buckets for the current actor."""
        buckets: List[Dict[str, Any]] = []

        # Base action labels (helps simple/random bots):
        if to_call > 0:
            # Facing a bet: fold/call available
            buckets.append({"label": "fold", "target": 0})
            buckets.append({"label": "call", "target": to_call})
        else:
            # No bet to call: check available
            buckets.append({"label": "check", "target": 0})

        # True SB open detection
        sb_open_pf = self._is_true_sb_open_pf(actor_seat)

        if to_call == 0 or sb_open_pf:
            # Opening/stab sizes (open raise or postflop bet)
            for mult in (2.2, 2.5, 3.0):
                target = int(round(mult * self.bb))
                buckets.append(
                    {"label": f"{mult:.1f}x", "target": max(target, self.bb)}
                )
        else:
            # Facing a bet/raise -> raise sizes (suffix 'R'), TOTAL commitment
            base = max(self._last_raise_size or 0, self.bb)
            for mult in (2.5, 3.0):
                target = int(self._current_price + round(mult * base))
                buckets.append({"label": f"{mult:.1f}xR", "target": target})

        # Always include jam (all-in sentinel)
        buckets.append({"label": "jam", "target": 10**12})

        buckets.sort(key=lambda b: b["target"])
        return buckets

    def _snap_to_bucket(
        self, requested_total: int, to_call: int, actor_seat: Optional[int] = None
    ) -> Dict[str, Any]:
        # Compute all buckets, but exclude non-bet actions ('check'/'fold') from snapping candidates
        buckets_all = self._allowed_buckets_data(to_call, actor_seat)
        candidates = [b for b in buckets_all if b["label"] not in ("check", "fold")]

        jam_bucket = next((b for b in candidates if b["label"] == "jam"), None)
        nonjam = [b for b in candidates if b["label"] != "jam"]
        nonjam_targets = [b["target"] for b in nonjam]
        max_non_jam = max(nonjam_targets) if nonjam_targets else 0

        # Force jam if wildly large request
        jam_floor = max(self.bb * 100, max_non_jam * 20)
        if requested_total >= jam_floor:
            best = jam_bucket or (
                max(nonjam, key=lambda b: b["target"])
                if nonjam
                else {"label": "jam", "target": int(to_call)}
            )
        else:
            search_space = candidates if candidates else buckets_all
            best = min(
                search_space,
                key=lambda b: (
                    abs(int(b["target"]) - int(requested_total)),
                    int(b["target"]),
                ),
            )

        return {
            "target": int(best["target"]),
            "snapped": int(requested_total) != int(best["target"]),
            "bucket_label": best["label"],
            "allowed_buckets": [b["label"] for b in buckets_all],
        }

    def _rotate_to(self, seat: Optional[int]) -> None:
        """Set next actor and compute amount to call (or clear turn if None)."""
        self._next_to_act = seat
        if seat is None:
            self._to_call_next = 0
            return
        self._to_call_next = max(0, self._current_price - self._committed[seat])

    def _compute_min_raise_total(self, seat: int, to_call: int) -> int:
        """
        Minimum TOTAL COMMITMENT required for the current actor to make a valid raise.
        - If to_call > 0: current_price + max(bb, last_raise_size)
        - If to_call == 0: current_price + max(bb, last_raise_size) (min open)
        """
        base_size = max(self.bb, self._last_raise_size or self.bb)
        return int(self._current_price + base_size)

    def _guard_pot_monotonic(self, new_total: int) -> None:
        """Ensure pot_total is non-decreasing within a single hand."""
        # If hand epoch changed (new hand), reset guard baseline
        if self._pot_guard_hand_epoch != self.hand_id:
            self._pot_guard_hand_epoch = self.hand_id
            self._pot_guard_prev = new_total
            return
        if new_total < self._pot_guard_prev:
            raise ValueError(
                f"pot_total decreased: {self._pot_guard_prev} -> {new_total}"
            )
        self._pot_guard_prev = new_total

    def _recalc_pot_total(self) -> None:
        """Running pot as the sum of all players' committed chips."""
        new_total = int(sum(self._committed))
        self._pot_total = new_total
        # Guard within-hand monotonicity
        self._guard_pot_monotonic(new_total)

    def _advance_street(self) -> None:
        """HU: preflop -> flop -> turn -> river -> showdown; set first actor."""
        if self._street == "preflop":
            self._street = "flop"
        elif self._street == "flop":
            self._street = "turn"
        elif self._street == "turn":
            self._street = "river"
        elif self._street == "river":
            self._street = "showdown"
        else:
            self._street = "showdown"

        # Reset raise tracking
        self._last_raise_size = 0
        self._raises_this_round = 0
        # On a new betting round, the current price is whatever everyone has committed so far,
        # which keeps to_call at 0 for the first actor of the new street.
        self._current_price = max(self._committed) if self._committed else 0

        # Deal board for the new street
        if self._street in ("flop", "turn", "river"):
            self._deal_board_to_street()

        # First to act postflop in HU is always the seat left of the button (bb_seat).
        if self._street in ("flop", "turn", "river"):
            self._rotate_to(self.bb_seat)
        else:
            # showdown: no more actions
            self._rotate_to(None)

    def _maybe_close_round_after_check(self, seat: int) -> None:
        """If we see check–check with no bet, close the round."""
        prev = self._last_action
        if prev and prev.type == "check" and prev.seat != seat:
            # Two consecutive checks close the round
            self._advance_street()

    def _close_round_after_call(self) -> None:
        """Call facing a bet/raise closes the round in HU."""
        # Ensure both are at the same price
        self._current_price = max(self._committed)
        self._recalc_pot_total()
        self._advance_street()

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
        if seats <= 0:
            raise ValueError("seats must be > 0")
        if len(stacks) != seats:
            raise ValueError("stacks length must equal seats")
        self.seats = seats
        self.sb = sb
        self.bb = bb
        self.ante = ante
        self.base_seed = base_seed
        # Reset per-hand state
        self.hand_id = 0
        self.button = -1
        self.sb_seat = None
        self.bb_seat = None
        self._street = "preflop"
        self._deck_seed = None
        self._next_to_act = None
        self._to_call_next = 0
        self._last_raise_size = 0
        self._raises_this_round = 0
        self._committed = [0] * seats
        self._current_price = 0
        self._players_holes = []
        self._deck = []
        self._board = []
        self._pot_total = 0
        self._last_action = None
        # Reset pot guard baseline
        self._pot_guard_prev = 0
        self._pot_guard_hand_epoch = 0

    def start_hand(self) -> str:
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
        self._last_raise_size = self.bb  # baseline for min open computation
        self._raises_this_round = 0
        # Post blinds into commitments and pot
        self._committed = [0] * self.seats
        if self.sb_seat is None or self.bb_seat is None:
            raise RuntimeError("blind seats not set")
        self._committed[self.sb_seat] = self.sb
        self._committed[self.bb_seat] = self.bb
        self._current_price = self.bb
        # Reset pot guard to current hand epoch before first pot calc
        self._pot_guard_hand_epoch = self.hand_id
        self._pot_guard_prev = 0
        self._recalc_pot_total()  # pot = sb + bb; guarded per-hand (0 -> blinds is OK)
        # Determine first actor: HU preflop -> SB acts first; multiway -> seat after BB
        self._rotate_to(self.sb_seat if self.seats == 2 else (self.bb_seat + 1) % self.seats)  # type: ignore[arg-type]
        # Build deterministic seed for deck
        self._deck_seed = (
            f"{self.base_seed}:{self.hand_id}" if self.base_seed is not None else None
        )
        # Deal hole cards deterministically and retain deck
        rng = self._seeded_rng(self._deck_seed or f"default:{self.hand_id}")
        self._deck = self._new_shuffled_deck(rng)
        self._board = []
        self._players_holes = []
        for _seat in range(self.seats):
            self._players_holes.append([self._deck.pop(), self._deck.pop()])
        # Clear last action
        self._last_action = None
        return f"H{self.hand_id}"

    def next_actor(self) -> Optional[Dict[str, Any]]:
        # Return an empty mapping when no actor is due, so callers can safely do .get(...)
        if self._next_to_act is None:
            return {}
        seat = int(self._next_to_act)
        to_call = int(self._to_call_next)
        buckets = self._allowed_buckets_data(to_call, actor_seat=self._next_to_act)
        return {
            "seat": seat,
            "to_call": to_call,
            "min_raise": int(self._compute_min_raise_total(seat, to_call)),
            "allowed_buckets": [b["label"] for b in buckets],
        }

    def apply_action(
        self, seat: int, action: str, amount: Optional[int] = None
    ) -> None:
        # Reject actions after showdown
        if self._street == "showdown":
            return
        # Ignore out-of-turn actions
        if seat != self._next_to_act:
            return

        action_l = (action or "").lower().strip()
        to_call = int(self._to_call_next)

        # ----- Fold -----
        if action_l == "fold":
            # Opponent wins the pot immediately; end hand
            self._last_action = _LastAction(seat=seat, type="fold")
            self._rotate_to(None)
            self._street = "showdown"
            # pot_total already reflects committed
            return

        # ----- Check -----
        if action_l == "check":
            if to_call != 0:
                raise ValueError("illegal check facing to_call")

            # Heads-up preflop pattern: SB called, BB checks -> deal flop, BB acts first.
            if self.seats == 2 and self._street == "preflop" and seat == self.bb_seat:
                last = self._last_action
                last_was_sb_call = (
                    isinstance(last, _LastAction)
                    and last.type == "call"
                    and last.seat == self.sb_seat
                )
                if last_was_sb_call:
                    # Move to flop and deal board
                    self._street = "flop"
                    self._last_raise_size = 0
                    self._raises_this_round = 0
                    self._current_price = max(self._committed) if self._committed else 0
                    self._deal_board_to_street()
                    if self.bb_seat is not None:
                        self._next_to_act = int(self.bb_seat)
                        self._to_call_next = max(
                            0,
                            int(self._current_price)
                            - int(self._committed[self.bb_seat]),
                        )
                    else:
                        self._next_to_act = None
                        self._to_call_next = 0
                    self._last_action = _LastAction(seat=seat, type="check")
                    return

            # --- Postflop/general: two consecutive checks close the round ---
            prev = self._last_action
            if prev and prev.type == "check" and prev.seat != seat:
                # Record this check and advance the street
                self._last_action = _LastAction(seat=seat, type="check")
                # Everyone is matched; keep price as the max committed
                self._current_price = max(self._committed) if self._committed else 0
                self._recalc_pot_total()
                self._advance_street()
                return

            # Otherwise, rotate to the opponent
            nxt = self.bb_seat if seat == self.sb_seat else self.sb_seat
            self._next_to_act = int(nxt) if nxt is not None else None
            if self._next_to_act is not None:
                self._to_call_next = max(
                    0,
                    int(self._current_price) - int(self._committed[self._next_to_act]),
                )
            else:
                self._to_call_next = 0

            self._last_action = _LastAction(seat=seat, type="check")
            return

        # ----- Call -----
        if action_l == "call":
            if to_call <= 0:
                # Treat as check redundancy safeguard
                self.apply_action(seat, "check")
                return

            # Match current price
            self._committed[seat] = self._current_price
            self._recalc_pot_total()
            self._last_action = _LastAction(seat=seat, type="call", committed=to_call)

            # HU preflop special-case: SB call does NOT close the round; BB still acts.
            if self.seats == 2 and self._street == "preflop" and seat == self.sb_seat:
                self._rotate_to(self.bb_seat)
                return

            # Otherwise, a call closes the betting round in HU.
            self._close_round_after_call()
            return

        # ----- Bet/Raise -----
        if action_l in ("bet", "raise"):
            if amount is None or not isinstance(amount, int):
                raise ValueError(
                    "bet/raise requires integer 'amount' (total commitment)"
                )

            # Detect true SB open (normalize verb to 'bet' even though to_call>0 due to blinds)
            is_sb_open_pf = self._is_true_sb_open_pf(seat)

            snap = self._snap_to_bucket(
                requested_total=amount, to_call=to_call, actor_seat=seat
            )
            committed_total = int(snap["target"])

            # --- Enforce min-raise total FIRST (tests expect 'min-raise' wording) ---
            min_total_required = int(
                self._current_price + max(self.bb, self._last_raise_size or self.bb)
            )
            if committed_total < min_total_required:
                raise ValueError(
                    f"min-raise not met: need ≥ {min_total_required}, got {committed_total}"
                )

            # Compute delta vs current table price (true raise size)
            delta = committed_total - int(self._current_price)
            # (No extra <=0 guard needed here; min-raise implies delta > 0)

            # Update raise state using the true delta
            self._last_raise_size = max(int(delta), self.bb)
            self._raises_this_round = (
                1
                if to_call == 0 and self._raises_this_round == 0
                else min(self._raises_this_round + 1, 99)
            )

            # Update commitment and price
            self._committed[seat] = committed_total
            self._current_price = committed_total
            self._recalc_pot_total()

            # Rotate to opponent
            nxt = self._opponent_of(seat)
            self._rotate_to(nxt)

            # Normalize verb for last_action:
            # - "bet" for postflop to_call==0 OR true HU SB open preflop
            # - "raise" otherwise
            verb = "bet" if (to_call == 0 or is_sb_open_pf) else "raise"

            # Record last action
            self._last_action = _LastAction(
                seat=seat,
                type=verb,
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
        # Snapshot board by street (always present)
        board = {
            "flop": self._board[:3] if len(self._board) >= 3 else [],
            "turn": self._board[:4] if len(self._board) >= 4 else [],
            "river": self._board[:5] if len(self._board) >= 5 else [],
        }
        return _GameSnap(
            table=tbl,
            players=players,
            street=self._street,
            deck_seed=self._deck_seed,
            pot_total=int(self._pot_total),
            last_action=self._last_action,
            board=board,
        )


# ---------------------------------------------------------------------------
# Singleton access

_ADAPTER: Optional[PokerKitAdapter] = None


def get_adapter() -> PokerKitAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = PokerKitAdapter()
    return _ADAPTER


__all__ = ["PokerKitAdapter", "get_adapter"]
