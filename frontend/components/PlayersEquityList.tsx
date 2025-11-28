// frontend/components/PlayersEquityList.tsx
// Compact list for displaying per-seat equities in multiway spots.
//
// This component is designed to render a small array of { seat, equity }
// entries, typically coming from an equity backend or a unified advice
// payload wrapper in the frontend. The hero seat can be highlighted for
// quick scanning in multiway pots.

import React from 'react';

/** Minimal per-seat equity entry used by this component. */
export interface PlayerEquityEntry {
  /** Table seat index. */
  seat: number;
  /** Equity for this seat, 0..1. */
  equity: number;
}

export interface PlayersEquityListProps {
  /** Per-seat equity entries (0–1 each). */
  players: PlayerEquityEntry[] | null | undefined;
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
              {isHero && (
                <span className="ml-1 text-[0.7rem] uppercase tracking-wide">
                  Hero
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default PlayersEquityList;
