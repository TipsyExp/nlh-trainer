// frontend/types/advice.ts
// Types for the unified Advice V1 payload returned by /api/coach/advice.
//
// This is shaped to match the real backend JSON, e.g.:
//
// {
//   "version": 1,
//   "status": "ok",
//   "meta": { "street": "flop", "n_players": 2, "hero_seat": 0, "source": "equity" },
//   "recommendation": { "bucket": "2.2x", "strategy_bar": [ { "action": "2.2x", "weight": 1 } ] },
//   "equity": { "backend": null, "mode": null, "hero": 0.63705, ... },
//   "thresholds": { "pot_odds": null, "spr": null, "ev_hint": null },
//   "rationale": "Hero equity ≈ ..."
// }

export type AdviceStatus = 'ok' | 'skipped' | 'error' | 'unavailable';

/** Street literal set, matching backend semantics. */
export type AdviceStreet =
  | 'preflop'
  | 'flop'
  | 'turn'
  | 'river'
  | 'showdown'
  | 'unknown';

/** Hero’s logical table position. */
export type HeroPosition =
  | 'BTN'
  | 'SB'
  | 'BB'
  | 'UTG'
  | 'HJ'
  | 'CO'
  | 'unknown';

/** Mixed strategy over action labels. Keys are bucket labels. */
export type ActionMix = Record<string, number>;

export interface AdviceStrategyPart {
  action: string;
  weight: number;
}

/**
 * The coach’s recommendation for this spot.
 *
 * The backend currently sends:
 *   recommendation.bucket        – canonical chosen bucket/action id
 *   recommendation.strategy_bar  – [{ action, weight }, ...]
 *
 * Early prototypes used:
 *   recommendation.primary_action
 *   recommendation.action_mix
 *
 * We support both for compatibility.
 */
export interface AdviceRecommendation {
  /** Canonical bucket/action id, e.g. "fold", "call", "2.5x", "jam". */
  bucket?: string;

  /** Backwards-compatible alias used in early drafts. */
  primary_action?: string;

  /** Canonical strategy bar from backend. */
  strategy_bar?: AdviceStrategyPart[];

  /** Optional map-form mix used by older code. */
  action_mix?: ActionMix;

  /** Optional sizing hint (rarely populated). */
  sizing_hint?: string | null;
}

/**
 * Per-seat equity entry (multiway support).
 * Not always present; often only hero is returned.
 */
export interface AdviceEquityPlayer {
  seat: number;
  equity: number;
}

/**
 * Equity block from the backend.
 *
 * In your current payload this looks like:
 *   "equity": {
 *     "backend": null,
 *     "mode": null,
 *     "hero": 0.63705,
 *     "players": null,
 *     "vs_field": null,
 *     "exact": null,
 *     "iters": null
 *   }
 */
export interface AdviceEquity {
  backend: string | null;
  mode: string | null;
  hero: number | null;
  players: AdviceEquityPlayer[] | null;
  vs_field: unknown | null;
  exact: boolean | null;
  iters: number | null;
  /** Optional text comment, if backend provides one. */
  comment?: string | null;
}

/**
 * Thresholds / pot-odds hints attached to the equity.
 */
export interface AdviceThresholds {
  /** Pot odds required equity to continue (0..1). */
  pot_odds?: number | null;

  /** Minimum equity required to call given the price (0..1). */
  min_equity_to_call?: number | null;

  /** Stack-to-pot ratio, if provided. */
  spr?: number | null;

  /** Optional EV hint string from backend. */
  ev_hint?: string | null;
}

/**
 * Optional richer context block. Not all fields will necessarily be
 * populated yet; everything is optional on purpose.
 */
export interface AdviceContext {
  street?: AdviceStreet | string;
  hero_position?: HeroPosition | string;
  hero_seat?: number;
  hero_cards?: string[] | null;
  board?: string[];
  pot_size?: number;
  to_call?: number;
  stack_effective?: number | null;
  allowed_buckets?: string[];
}

/**
 * Light-weight metadata; superseded by `context` when present.
 * This mirrors the `meta` object you see in the JSON.
 */
export interface AdviceMeta {
  street?: AdviceStreet | string;
  n_players?: number;
  hero_seat?: number;
  /** High-level backend source, e.g. "equity", "solver", "chart". */
  source?: string;
}

/**
 * Canonical Advice V1 envelope from the backend.
 *
 * This is what `/api/coach/advice` returns today.
 */
export interface AdvicePayloadV1 {
  version: 1;
  status: AdviceStatus;

  /** Simple metadata; new code should prefer `context` where available. */
  meta?: AdviceMeta;

  /** Optional richer, UI-focused context. */
  context?: AdviceContext;

  recommendation?: AdviceRecommendation;
  equity?: AdviceEquity;
  thresholds?: AdviceThresholds;

  /** Optional free-form explanation string. */
  rationale?: string | null;
}

/** Convenience alias used throughout the frontend. */
export type Advice = AdvicePayloadV1;
