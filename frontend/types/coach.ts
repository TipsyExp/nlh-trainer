// frontend/types/coach.ts
// Types for coach advice responses used in the guidance overlay.
//
// M3 NOTE – unified Advice payload
// --------------------------------
// The long-term goal is for the frontend to consume a single, cross-street
// "AdviceV1" payload from GET /api/coach/advice, as specified in
// docs/COACH-ADVICE-PAYLOAD.md. That unified payload is shaped roughly as:
//
//   {
//     version: 1,
//     status: 'ok' | 'disabled' | 'unsupported' | 'not_found' | 'timeout' | 'error',
//     meta: {
//       street: 'preflop' | 'flop' | 'turn' | 'river' | 'showdown' | 'unknown',
//       n_players: number,
//       hero_seat: number,
//       source: 'chart' | 'equity' | 'rule' | 'mixed'
//     },
//     recommendation?: {
//       bucket: string;
//       strategy_bar?: Array<{ action: string; weight: number }>;
//     },
//     equity?: { ... },
//     thresholds?: { pot_odds?: number; spr?: number },
//     rationale?: string
//   }
//
// This file does **not** define that full shape yet. Instead it documents the
// minimal advice structure currently used by the overlay, which corresponds
// to the "recommendation + rationale" slice of the unified AdviceV1 object.
// As we migrate the UI to the universal advice payload, these types will
// either:
//   * wrap the new AdviceV1 type, or
//   * be marked legacy and used only for the old /api/coach/preflop path.

/**
 * Indicates the origin of the advice. The backend may return other
 * sources beyond the known set; unknown values are retained as-is.
 *
 * In the unified AdviceV1 payload this value will live under:
 *   advice.meta.source
 * and the canonical set of values is documented in
 * docs/COACH-ADVICE-PAYLOAD.md.
 */
export type CoachSource =
  | 'chart'
  | 'equity'
  | 'rule'
  | 'fallback'
  | (string & {});

/**
 * A single segment of the coach's suggested strategy bar.
 *
 * Each entry represents:
 *   - `action`: a bucket label (e.g. "fold", "call", "2.5x", "3.0xR", "jam")
 *   - `pct`:   the fraction of time that action should be taken (0–1)
 *
 * The overlay converts `pct` into percentage widths for display. When we
 * adopt the unified AdviceV1 payload, this will correspond to one element
 * of `advice.recommendation.strategy_bar`.
 */
export interface StrategyPart {
  action: string;
  pct: number;
}

/**
 * Minimal coach advice payload currently expected by the frontend.
 *
 * Fields:
 *   - `bucket`:        the primary recommended action bucket (fold, call,
 *                      raise_x.x, jam, etc.).
 *   - `strategy_bar`:  optional finer-grained distribution that the UI can
 *                      visualise as a strategy bar.
 *   - `rationale`:     optional free-form explanation used for helper text
 *                      and tooltips.
 *   - `raw`:           passthrough for any extra backend data (debug only).
 *
 * Relationship to unified AdviceV1:
 *   - maps to `advice.meta.source`
 *   - maps to `advice.recommendation.bucket`
 *   - maps to `advice.recommendation.strategy_bar` (after adapting shape)
 *   - maps to `advice.rationale`
 */
export interface CoachAdvice {
  source: CoachSource;
  bucket: string;
  strategy_bar?: StrategyPart[];
  rationale?: string;
  raw?: unknown;
}
