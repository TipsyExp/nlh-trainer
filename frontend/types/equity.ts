// frontend/types/equity.ts
// Types mirroring the raw equity response from the backend.
//
// The backend exposes a POST /api/equity endpoint that returns a structured
// summary of players' equities given a set of inputs. In particular the
// response includes per-player win/tie percentages, whether the calculation
// was exact or Monte Carlo, and the number of iterations used.
//
// These interfaces are used by tools and dev UIs that call /api/equity
// directly. The main decision overlay, however, should prefer the unified
// coach advice payload (see `frontend/types/advice.ts`, `AdviceEquity`)
// rather than depending on this low-level response shape.

/**
 * Calculation mode for the equity engine.
 *
 * - 'hands'  – all players have fixed hands.
 * - 'ranges' – at least one player is specified as a range.
 *
 * This mirrors the backend's EquityResult.mode field.
 */
export type EquityMode = "hands" | "ranges";

/**
 * Per-player equity summary as returned by /api/equity.
 *
 * Note:
 *   - Players are reported in seat order; the caller must track which
 *     seat index corresponds to which hero/villain.
 *   - The higher-level coach advice payload (`AdviceEquityPlayer`) adds
 *     an explicit `seat` field for multiway display.
 */
export interface EquityPlayer {
  /** Probability of winning outright (e.g. 0.45 for 45%). */
  win: number;
  /** Probability of tying (e.g. 0.02 for 2%). */
  tie: number;
  /** Overall equity including ties (e.g. 0.46 for 46%). */
  equity: number;
}

/**
 * Response shape for POST /api/equity.
 *
 * This is intentionally lower-level than the unified coaching advice
 * payload. New UI work (especially the guidance overlay) should use
 * `AdviceV1` / `AdviceEquity` instead, and treat this type as a
 * dev/utility interface for direct equity inspection.
 */
export interface EquityResponse {
  /** True when the server computed the equity successfully. */
  ok: boolean;
  /** Name of the backend that performed the calculation. */
  backend: string;
  /**
   * Calculation mode:
   *   - 'hands'  when all players have fixed hands.
   *   - 'ranges' when at least one player is a range.
   */
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
  /** Per-player results, in seat order. */
  players: EquityPlayer[];
  /** Optional raw payload returned by the backend. */
  raw?: Record<string, unknown>;
}
