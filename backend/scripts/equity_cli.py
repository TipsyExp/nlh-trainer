# backend/scripts/equity_cli.py
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Tuple

from backend.services.equity.base import PlayerSpec, Card
from backend.services.equity.service import EquityService

_CARD_RE = re.compile(r"^[2-9TJQKA][cdhs]$")


def parse_cardpair(s: str) -> Tuple[Card, Card]:
    """
    Parse a 4-character string like 'AhAd' into ('Ah', 'Ad').
    """
    s = s.strip()
    if len(s) != 4:
        raise argparse.ArgumentTypeError("hand must look like AhAd (4 characters)")
    c1, c2 = s[:2], s[2:]
    for c in (c1, c2):
        if not _CARD_RE.match(c):
            raise argparse.ArgumentTypeError(f"invalid card in --hand: {c!r}")
    if c1 == c2:
        raise argparse.ArgumentTypeError("hand cannot contain duplicate cards")
    return c1, c2


def parse_board_or_dead(s: str) -> List[Card]:
    """
    Parse a flat card string like 'AsKd2c' into ['As', 'Kd', '2c'].

    Empty string -> [].
    """
    s = s.strip()
    if not s:
        return []
    if len(s) % 2 != 0:
        raise argparse.ArgumentTypeError(
            f"board/dead string must have even length; got {len(s)}"
        )
    out: List[Card] = [s[i : i + 2] for i in range(0, len(s), 2)]
    for c in out:
        if not _CARD_RE.match(c):
            raise argparse.ArgumentTypeError(f"invalid card: {c!r}")
    # simple dup check within the list itself
    if len(out) != len(set(out)):
        raise argparse.ArgumentTypeError("duplicate cards provided")
    return out


def _validate_no_collisions_if_fixed_hands(
    hands: List[Tuple[Card, Card]], board: List[Card], dead: List[Card]
) -> None:
    # ensure no card appears in multiple places when we know all exact cards
    seen: set[Card] = set()

    def _add(c: Card, where: str) -> None:
        if c in seen:
            raise argparse.ArgumentTypeError(f"duplicate card {c!r} across {where}")
        seen.add(c)

    for i, (a, b) in enumerate(hands):
        _add(a, f"players/board/dead (player {i} hand)")
        _add(b, f"players/board/dead (player {i} hand)")
    for c in board:
        _add(c, "players/board/dead (board)")
    for c in dead:
        _add(c, "players/board/dead (dead)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Equity calculator (hands or ranges) using the backend's EquityService",
    )

    mode_group = ap.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--hand",
        action="append",
        type=parse_cardpair,
        help="Two-card hand like AhAd. Repeat per player.",
    )
    mode_group.add_argument(
        "--range",
        dest="ranges",
        action="append",
        help="Range string for each player (pbots_calc syntax, e.g. 'JJ+', 'random').",
    )

    ap.add_argument(
        "--board",
        default="",
        help="Board cards as a flat string, e.g. AsKd2c (optional).",
    )
    ap.add_argument(
        "--dead",
        default="",
        help="Dead cards as a flat string, e.g. 7h7d (optional).",
    )
    ap.add_argument(
        "--iters",
        type=int,
        default=None,
        help="Monte Carlo iterations for non-exact backends (optional).",
    )
    ap.add_argument(
        "--exact",
        action="store_true",
        help="Request exact enumeration where supported.",
    )
    ap.add_argument(
        "--timeout-ms",
        type=int,
        default=None,
        help="Soft timeout hint for backends that support it (optional).",
    )
    ap.add_argument(
        "--policy",
        choices=["auto", "pokerkit", "henry", "pbots"],
        default=os.getenv("EQUITY_BACKEND_POLICY", "auto"),
        help="Backend selection policy (default: %(default)s).",
    )

    return ap


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Force policy via env before constructing the service
    os.environ["EQUITY_BACKEND_POLICY"] = args.policy

    players: List[PlayerSpec] = []

    if args.hand:
        # Hands-only mode
        if len(args.hand) < 2:
            parser.error("when using --hand, provide at least two --hand values")
        board = parse_board_or_dead(args.board)
        dead = parse_board_or_dead(args.dead)
        _validate_no_collisions_if_fixed_hands(args.hand, board, dead)
        for h in args.hand:
            players.append(PlayerSpec(hand=h))
    else:
        # Ranges mode
        if not args.ranges or len(args.ranges) < 2:
            parser.error("when using --range, provide at least two --range values")
        board = parse_board_or_dead(args.board)
        dead = parse_board_or_dead(args.dead)
        # Overlap between board and dead is still invalid
        if set(board) & set(dead):
            parser.error("a card cannot be both on the board and in dead cards")
        for r in args.ranges:
            r = (r or "").strip()
            if not r:
                parser.error("range strings must be non-empty")
            players.append(PlayerSpec(range=r))

    svc = EquityService()

    try:
        res = svc.calc_equity(
            players=players,
            board=board,
            dead=dead,
            iters=args.iters,
            exact=bool(args.exact),
            timeout_ms=args.timeout_ms,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    # Summary header
    print(
        f"backend: {res.backend} | "
        f"mode: {res.mode} | "
        f"players: {res.n_players} | "
        f"exact: {res.exact} | "
        f"iters: {res.iters}"
    )

    # Per-player lines
    for i, p in enumerate(res.per_player):
        equity = float(p.get("equity", 0.0))
        win = int(p.get("win", 0))
        tie = int(p.get("tie", 0))
        print(f"P{i}: equity={equity:.4f} win={win} tie={tie}")

    # Optional backend extras
    if res.raw:
        sims = res.raw.get("simulations") or res.raw.get("trials")
        if sims:
            print(f"(samples: {sims})")


if __name__ == "__main__":
    main()
