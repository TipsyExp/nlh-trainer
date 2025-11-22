// frontend/types/coach.ts
// Types for coach advice responses used in the guidance overlay.
//
// M3 NOTE – unified Advice payload
// --------------------------------
// The long-term goal is for the frontend to consume a single, cross-street
// `AdviceV1` payload from GET /api/coach/advice, as specified in
// docs/COACH-ADVICE-PAYLOAD.md and mirrored in `frontend/types/advice.ts`.
//
// That unified payload looks roughly like:
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
// This file currently exposes:
//
//   * Legacy preflop-only coach types (`CoachAdvice`, `CoachSource`,
//     and its own `StrategyPart` with `pct`).
//   * Re-exports of the new unified Advice types from `./advice` for
//     convenience during migration.
//
// New code should prefer importing from `frontend/types/advice`, or
// from here via the `Advice*` re-exports below. The legacy types will
// be kept only for the old `/api/coach/preflop` path and dev tools.

/**
 * Re-export the unified Advice types so existing imports from
 * `frontend/types/coach` can gradually migrate without needing to
 * know about `frontend/types/advice` immediately.
 *
 * Note: StrategyPart from `advice.ts` is exported as `AdviceStrategyPart`
 * to avoid clashing with the legacy `StrategyPart` defined below.
 */
export type {
  AdviceStatus,
  AdviceStreet,
  AdviceSource,
  AdviceRecommendation,
  AdviceEquityPlayer,
  AdviceEquity,
  AdviceThresholds,
  AdviceMeta,
  AdviceV1,
  Advice,
} from "./advice";
export type { StrategyPart as AdviceStrategyPart } from "./advice";

/**
 * Indicates the origin of the advice for the legacy preflop-only
 * coach payload. The backend may return other sources beyond the
 * known set; unknown values are retained as-is.
 *
 * In the unified AdviceV1 payload the canonical source lives under:
 *   advice.meta.source
 * and its type is `AdviceSource` (see `frontend/types/advice.ts`).
 *
 * The `"fallback"` value here is legacy and specific to the old
 * preflop route; new AdviceV1 payloads will typically use `"rule"`
 * instead for similar semantics.
 */
export type CoachSource =
  | "chart"
  | "equity"
  | "rule"
  | "fallback"
  | (string & {});

/**
 * A single segment of the coach's suggested strategy bar (legacy shape).
 *
 * Each entry represents:
 *   - `action`: a bucket label (e.g. "fold", "call", "2.5x", "3.0xR", "jam")
 *   - `pct`:   the fraction of time that action should be taken (0–1)
 *
 * The overlay converts `pct` into percentage widths for display.
 *
 * In the unified AdviceV1 payload, this concept maps to one element of
 * `advice.recommendation.strategy_bar`, where the field is named
 * `weight` instead of `pct`. Callers that still use this legacy type
 * should adapt accordingly when they migrate.
 */
export interface StrategyPart {
  action: string;
  pct: number;
}

/**
 * Minimal coach advice payload currently expected by parts of the frontend
 * for the legacy `/api/coach/preflop` endpoint.
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
 *   - `source`        → `advice.meta.source`
 *   - `bucket`        → `advice.recommendation.bucket`
 *   - `strategy_bar`  → `advice.recommendation.strategy_bar`
 *                      (after adapting `{ pct }` → `{ weight }`)
 *   - `rationale`     → `advice.rationale`
 */
export interface CoachAdvice {
  source: CoachSource;
  bucket: string;
  strategy_bar?: StrategyPart[];
  rationale?: string;
  raw?: unknown;
}
