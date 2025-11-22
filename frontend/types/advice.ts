// frontend/types/advice.ts

/**
 * Unified coaching advice payload (v1).
 *
 * This mirrors the backend `AdviceV1` schema in `backend.schemas.advice`
 * and is used by the decision overlay for ALL streets (preflop + postflop,
 * HU + multiway).
 *
 * Notes:
 * - Backend always returns `version = 1`.
 * - HTTP status codes are mostly for “route disabled / missing”; normal
 *   runtime states are expressed via `AdviceStatus` on the payload itself.
 */

/** Overall status of the advice payload, independent of HTTP status. */
export type AdviceStatus =
  | "ok"          // Advice is actionable.
  | "disabled"    // Coach disabled by config / env.
  | "unsupported" // Spot not yet supported by this coach.
  | "not_found"   // Hand/idx or context could not be resolved.
  | "timeout"     // (Reserved) Equity / solver timed out.
  | "error";      // Unexpected backend or equity error.

/** Street literal set, matching backend `StreetLiteral`. */
export type AdviceStreet =
  | "preflop"
  | "flop"
  | "turn"
  | "river"
  | "showdown"
  | "unknown";

/** Source of the recommendation. */
export type AdviceSource = "chart" | "equity" | "rule" | "mixed";

/** Single bar in the strategy breakdown. */
export interface StrategyPart {
  /** Canonical bucket label, e.g. "fold", "call", "check", "2.5x", "2.5xR", "jam". */
  action: string;
  /** Relative weight / probability in [0, 1]. */
  weight: number;
}

/** Recommended action + strategy mix. */
export interface AdviceRecommendation {
  /** Primary bucket to recommend to the user. */
  bucket: string;
  /**
   * Strategy bar components.
   *
   * In v1 this is usually a single-entry array with weight=1.0, but the
   * type allows for richer mixes (e.g. call/raise splits) later.
   */
  strategy_bar?: StrategyPart[] | null;
}

/** Per-player equity entry used in multiway spots. */
export interface AdviceEquityPlayer {
  /** Table seat index. */
  seat: number;
  /** Equity for this seat, 0..1. */
  equity: number;
}

/** Equity section of the advice payload. */
export interface AdviceEquity {
  /**
   * Backend name, e.g. "ompeval", "eval7", "pokerkit".
   * May be null when the coach does not expose it (e.g. preflop chart-only).
   */
  backend: string | null;

  /**
   * Equity evaluation mode:
   * - "hands": all players specified by concrete hands.
   * - "ranges": one or more players specified as ranges.
   */
  mode: "hands" | "ranges" | null;

  /** Hero equity in [0, 1]. */
  hero: number;

  /**
   * Per-player equities (mainly for multiway).
   * In HU v1 this is often null.
   */
  players: AdviceEquityPlayer[] | null;

  /**
   * Hero equity vs the rest of the field combined.
   * For HU this is typically equal to `hero`.
   */
  vs_field: number | null;

  /** Whether the calculation was exact (true) or Monte Carlo (false), if known. */
  exact: boolean | null;

  /** Number of iterations used for Monte Carlo backends, if applicable. */
  iters: number | null;
}

/** Thresholds and pricing info derived from the current spot. */
export interface AdviceThresholds {
  /**
   * Required equity to continue given the current price:
   *
   *   pot_odds = to_call / (pot_total + to_call)
   *
   * Using the convention that `pot_total` is the pot size *before* hero acts.
   */
  pot_odds: number | null;

  /**
   * Stack-to-pot ratio (SPR) if/when the backend exposes it.
   * Currently unused by the coach, but reserved for future UI.
   */
  spr: number | null;
}

/** Metadata about the decision and how advice was produced. */
export interface AdviceMeta {
  /** Street at this decision. */
  street: AdviceStreet;
  /** Number of players still in the hand at this decision. */
  n_players: number;
  /** Hero's seat index. */
  hero_seat: number;
  /** High-level source of this advice (chart, equity, rule, mixed). */
  source: AdviceSource;
}

/**
 * Versioned unified advice payload.
 *
 * This is the single shape returned by `/api/coach/advice` across all
 * streets and player counts.
 */
export interface AdviceV1 {
  /** Schema version. Currently always 1. */
  version: 1;

  /** High-level status for this advice object. */
  status: AdviceStatus;

  /** Decision metadata. */
  meta: AdviceMeta;

  /**
   * Recommended action and strategy mix.
   * May be null when the spot is disabled/unsupported/error.
   */
  recommendation: AdviceRecommendation | null;

  /**
   * Equity information if the coach used an equity backend.
   * Null for pure chart/rule-only advice.
   */
  equity: AdviceEquity | null;

  /**
   * Pot odds / SPR thresholds derived from the decision context.
   * Null when not applicable or unavailable.
   */
  thresholds: AdviceThresholds | null;

  /**
   * Human-readable explanation of the recommendation.
   * May be null in purely mechanical or error cases.
   */
  rationale: string | null;
}

/** Convenience alias for “current” advice type. */
export type Advice = AdviceV1;
