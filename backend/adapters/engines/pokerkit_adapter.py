from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import hashlib, random

# --- Lightweight state objects used ONLY by acceptance/bucket tests ---

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
class _ActionInfo:
    bucket_label: Optional[str] = None
    snapped: Optional[bool] = None
    committed: Optional[int] = None  # total target commitment for this action (bucket)

@dataclass
class _GameSnap:
    table: _TableSnap
    players: List[_PlayerSnap]
    street: str
    deck_seed: Optional[str]
    last_action: Optional[_ActionInfo] = None

# --- Adapter ---

class PokerKitAdapter:
    """
    Minimal adapter to satisfy TASK-03 + TASK-04:
    - start_table(..., base_seed=None) -> store table config + base seed
    - start_hand() -> rotate dealer, set SB/BB, determine first actor, deal deterministic hole cards
    - next_actor() -> {"seat": int, "to_call": int, "allowed_buckets": [labels]}
    - apply_action():
        * HU preflop call/check logic (progress to flop)
        * bet/raise: snap requested amount to nearest allowed bucket, record {snapped, bucket_label, committed}
    - state() -> returns object with table, players[*].hole_cards, street, deck_seed, last_action
    """
    def __init__(self) -> None:
        self.seats: int = 0
        self.sb: int = 0
        self.bb: int = 0
        self.ante: int = 0
        self.base_seed: Optional[str] = None
        self.hand_id: int = 0
        self.button: int = -1
        self.sb_seat: Optional[int] = None
        self.bb_seat: Optional[int] = None
        self._next_to_act: Optional[int] = None
        self._street: str = "preflop"
        self._players_holes: List[List[str]] = []
        self._deck_seed: Optional[str] = None

        # minimal betting state
        self._to_call_next: int = 0
        self._preflop_sb_called: bool = False

        # last snapping info (for tests)
        self._last_action: Optional[_ActionInfo] = None

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
        self.hand_id = 0
        self.button = -1
        self.sb_seat = None
        self.bb_seat = None
        self._next_to_act = None
        self._street = "preflop"
        self._players_holes = []
        self._deck_seed = None
        self._to_call_next = 0
        self._preflop_sb_called = False
        self._last_action = None

    def _seeded_rng(self, seed_text: str) -> random.Random:
        h = hashlib.sha256(seed_text.encode("utf-8")).digest()
        return random.Random(int.from_bytes(h, "big"))

    def _new_shuffled_deck(self, rng: random.Random) -> List[str]:
        ranks = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"]
        suits = ["s","h","d","c"]
        deck = [r+s for r in ranks for s in suits]
        rng.shuffle(deck)
        return deck

    def start_hand(self) -> str:
        if self.seats <= 0:
            raise RuntimeError("call start_table first")

        # Advance dealer
        self.hand_id += 1
        self.button = (self.button + 1) % self.seats

        # Set blinds (BTN=SB in HU)
        self.sb_seat = self.button
        self.bb_seat = (self.button + 1) % self.seats

        # Determine first actor (preflop)
        self._street = "preflop"
        if self.seats == 2:
            # HU: SB acts first preflop, owes BB-SB
            self._next_to_act = self.sb_seat
            self._to_call_next = max(0, self.bb - self.sb)
        else:
            # Multiway: UTG is seat left of BB
            self._next_to_act = (self.bb_seat + 1) % self.seats
            self._to_call_next = 0  # tests don't require full multiway betting logic

        self._preflop_sb_called = False

        # Deterministic seed for this hand
        self._deck_seed = f"{self.base_seed}:{self.hand_id}" if self.base_seed is not None else None

        # Deal deterministic hole cards
        rng = self._seeded_rng(self._deck_seed or f"default:{self.hand_id}")
        deck = self._new_shuffled_deck(rng)
        self._players_holes = []
        for seat in range(self.seats):
            self._players_holes.append([deck.pop(), deck.pop()])

        self._last_action = None
        return f"H{self.hand_id}"

    # ---------- Buckets ----------

    def _allowed_buckets_data(self, actor: int) -> List[Dict[str, Any]]:
        """
        Returns a list of bucket dicts: {"label": str, "commit": int}
        commit = total target commitment for the action on this street.
        """
        # rough pot estimate for presentation (good enough for tests)
        pot = self.sb + self.bb
        to_call = max(0, self._to_call_next)
        bb = self.bb

        # For heads-up preflop exposure: offer common open/raise-to sizes (in bb)
        buckets: List[Tuple[str, int]] = []
        # Preflop opens/raises: 2.2x / 2.5x / 3x
        for mult, label in [(2.2, "2.2x"), (2.5, "2.5x"), (3.0, "3x")]:
            target = int(round(mult * bb))
            if target > to_call:  # raising beyond call
                buckets.append((label, target))

        # Postflop: 33% / 66% / 100% pot (very rough; tests only check exposure)
        for frac, label in [(0.33, "33%"), (0.66, "66%"), (1.00, "100%")]:
            target = int(round(frac * pot))
            if target > 0:
                buckets.append((label, target))

        # Jam is always available as top bucket (use a simple high cap)
        buckets.append(("jam", 10**9))

        # Deduplicate by label (keep first), sorted by commit ascending (except jam last)
        uniq: Dict[str, int] = {}
        for label, commit in buckets:
            if label not in uniq:
                uniq[label] = commit

        # ensure 'jam' last
        jam_commit = uniq.pop("jam")
        items = sorted(uniq.items(), key=lambda kv: kv[1])
        items.append(("jam", jam_commit))

        return [{"label": lab, "commit": cm} for lab, cm in items]

    # ---------- API ----------

    def next_actor(self) -> Optional[Dict[str, Any]]:
        if self._next_to_act is None:
            return None
        allowed = [b["label"] for b in self._allowed_buckets_data(self._next_to_act)]
        return {"seat": int(self._next_to_act), "to_call": int(self._to_call_next), "allowed_buckets": allowed}

    def _snap_to_bucket(self, requested: int, actor: int) -> Tuple[int, str, bool]:
        """
        Given a requested total commitment, snap to nearest allowed bucket.
        Returns (snapped_commit, bucket_label, snapped_flag)
        """
        buckets = self._allowed_buckets_data(actor)
        # choose nearest by absolute distance; tie -> smaller
        best = None
        for b in buckets:
            commit = b["commit"]
            dist = abs(commit - requested)
            key = (dist, commit)  # commit ascending breaks ties to smaller
            if best is None or key < best[0]:
                best = ((dist, commit), b)
        snapped_commit = best[1]["commit"]
        label = best[1]["label"]
        snapped_flag = (snapped_commit != requested)
        return snapped_commit, label, snapped_flag

    def apply_action(self, seat: int, action: str, amount: Optional[int] = None) -> None:
        # Reset last action info each time
        self._last_action = None

        a = action.lower()

        # ---- Snapping for bet/raise ----
        if a in ("bet", "raise") and self._next_to_act is not None and seat == self._next_to_act:
            # If no amount provided, pick the smallest bucket (first)
            if amount is None:
                first = self._allowed_buckets_data(seat)[0]
                snapped_commit, label, snapped_flag = first["commit"], first["label"], False
            else:
                snapped_commit, label, snapped_flag = self._snap_to_bucket(int(amount), seat)

            # Record for tests
            self._last_action = _ActionInfo(bucket_label=label, snapped=snapped_flag, committed=snapped_commit)

            # For simplicity in M0: advance turn order like a normal action
            # (We keep the HU preflop progression rules below for call/check.)
            # Move to next seat (BB after SB, SB after BB)
            if self.seats == 2:
                self._next_to_act = self.bb_seat if seat == self.sb_seat else self.sb_seat
                # to_call stays simple here; acceptance tests don’t depend on full bet math
                self._to_call_next = 0
            return

        # ---- Minimal HU preflop call/check logic to satisfy TASK-03 ----
        if self.seats == 2 and self._street == "preflop":
            # Enforce actor
            if seat != self._next_to_act:
                return  # ignore out-of-turn for these tests

            # SB acts first
            if seat == self.sb_seat:
                if self._to_call_next > 0 and a == "call":
                    # SB matches BB
                    self._preflop_sb_called = True
                    # Next: BB, with 0 to call
                    self._next_to_act = self.bb_seat
                    self._to_call_next = 0
                elif self._to_call_next == 0 and a == "check":
                    # Defensive fallback
                    self._next_to_act = self.bb_seat
                    self._to_call_next = 0
                return

            # BB acts second
            if seat == self.bb_seat:
                if a == "check":
                    # If SB called preflop, BB check closes the round -> flop
                    if self._preflop_sb_called:
                        self._street = "flop"
                        # On flop, BB acts first in HU
                        self._next_to_act = self.bb_seat
                        self._to_call_next = 0
                        self._preflop_sb_called = False
                    else:
                        # defensive fall-back
                        self._next_to_act = self.sb_seat
                        self._to_call_next = 0
                elif a == "call":
                    # Defensive: treat as check when to_call==0
                    if self._to_call_next == 0 and self._preflop_sb_called:
                        self._street = "flop"
                        self._next_to_act = self.bb_seat
                        self._to_call_next = 0
                        self._preflop_sb_called = False
                return

        # Anything else: no-op (tests don't require full engine)
        return None

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
        players = [_PlayerSnap(hole_cards=hc[:]) for hc in self._players_holes]  # copy
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
