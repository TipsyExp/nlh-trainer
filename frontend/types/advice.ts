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

export type AdviceStatus =
  | 'ok'
  | 'error'
  | 'skipped'
  | 'unavailable'
  | 'disabled'
  | 'unsupported';

/**
 * High-level source label, as used by the backend in `meta.source`
 * (e.g. "equity", "solver", "chart", "noop"...).
 *
 * This is kept intentionally loose so dev tooling can treat it as a
 * simple human-readable string.
 */
export type AdviceSource = string;

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

/**
 * Generic strategy-part shape used by legacy coach types.
 * `types/coach.ts` re-exports this as `AdviceStrategyPart`.
 */
export interface StrategyPart {
  action: string;
  weight: number;
}

/** Alias kept for clarity in newer code. */
export type AdviceStrategyPart = StrategyPart;

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
 *
 * We also expose a few optional, more "UI-friendly" aliases so newer
 * components (like the DecisionHelpOverlay) can attach to them without
 * breaking older callers:
 *
 *   hero_vs_villain_equity  – alias for `hero`
 *   pot_odds                – often comes from thresholds; may be copied over
 *   min_equity_to_call      – same as above
 */
export interface AdviceEquity {
  backend: string | null;
  mode: string | null;
  hero: number | null;
  players: AdviceEquityPlayer[] | null;
  vs_field: unknown | null;
  exact: boolean | null;
  iters: number | null;

  /** Optional text comment, if backend or adapter provides one. */
  comment?: string | null;

  /** Optional normalised aliases used by newer UIs. */
  hero_vs_villain_equity?: number | null;
  pot_odds?: number | null;
  min_equity_to_call?: number | null;
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
  source?: AdviceSource;
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

  /** Optional richer, UI-focused context (future-facing). */
  context?: AdviceContext;

  /**
   * Optional explicit source object or label. Most current backends
   * only populate meta.source, but this gives UI code a stable place
   * to hang a human-readable "Source:" badge if we add it later.
   */
  source?: AdviceSource | null;

  recommendation?: AdviceRecommendation;
  equity?: AdviceEquity;
  thresholds?: AdviceThresholds;

  /** Optional free-form explanation string. */
  rationale?: string | null;
}

/** Convenience aliases used throughout the frontend. */
export type Advice = AdvicePayloadV1;
export type AdviceV1 = AdvicePayloadV1;
