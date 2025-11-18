// frontend/types/equity.ts
// Types mirroring the equity response from the backend.
//
// The backend exposes a POST /api/equity endpoint that returns a
// structured summary of the players' equities given a set of inputs.  In
// particular the response includes per‑player win/tie percentages,
// whether the calculation was exact or Monte Carlo, and the number of
// iterations used.  These interfaces allow the frontend to type
// check the equity response and surface useful information in the
// guidance overlay.

export type EquityMode = 'hands' | 'ranges';

export interface EquityPlayer {
  /** Probability of winning outright (e.g. 0.45 for 45%). */
  win: number;
  /** Probability of tying (e.g. 0.02 for 2%). */
  tie: number;
  /** Overall equity including ties (e.g. 0.46 for 46%). */
  equity: number;
}

export interface EquityResponse {
  /** True when the server computed the equity successfully. */
  ok: boolean;
  /** Name of the backend that performed the calculation. */
  backend: string;
  /** Calculation mode: 'hands' when all players have fixed hands, 'ranges' for range vs hand. */
  mode: EquityMode;
  /** Number of players included in the calculation. */
  n_players: number;
  /** The current board cards used in the calculation. */
  board: string[];
  /** Cards removed from the deck (e.g. burned or mucked). */
  dead: string[];
  /** True if the equity was computed exactly rather than via Monte Carlo simulation. */
  exact: boolean;
  /** Number of iterations used when `exact` is false. */
  iters: number | null;
  /** Per‑player results, in seat order. */
  players: EquityPlayer[];
  /** Optional raw payload returned by the backend. */
  raw?: Record<string, unknown>;
}
