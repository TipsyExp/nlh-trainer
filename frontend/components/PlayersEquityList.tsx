// frontend/components/PlayersEquityList.tsx
// Compact list for displaying per-seat equities in multiway spots.
//
// This component is designed to render the `players` array from the
// unified AdviceV1 payload (advice.equity.players), where each entry
// contains a seat index and that seat's overall equity. The hero seat
// can be highlighted for quick scanning in multiway pots.

import React from 'react';
import type { AdviceEquityPlayer } from '../types/advice';

export interface PlayersEquityListProps {
  /** Per-seat equity entries from advice.equity.players. */
  players: AdviceEquityPlayer[] | null | undefined;
  /** Optional hero seat; when provided, that row is highlighted. */
  heroSeat?: number | null;
}

export function PlayersEquityList({ players, heroSeat }: PlayersEquityListProps) {
  if (!players || players.length === 0) {
    return null;
  }

  return (
    <div className="text-xs text-gray-700">
      <ul className="space-y-0.5">
        {players.map((p) => {
          const isHero = heroSeat != null && p.seat === heroSeat;
          const eq = Number.isFinite(p.equity) ? p.equity : 0;
          const pct = Math.max(0, Math.min(1, eq)) * 100;

          return (
            <li
              key={p.seat}
              className={isHero ? 'font-semibold text-blue-700' : 'text-gray-700'}
            >
              <span className="mr-1">Seat {p.seat}:</span>
              <span>{pct.toFixed(1)}%</span>
              {isHero && <span className="ml-1 text-[0.7rem] uppercase tracking-wide">Hero</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default PlayersEquityList;
