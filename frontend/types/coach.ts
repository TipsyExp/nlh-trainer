// frontend/types/coach.ts
// Types for coach advice responses used in the guidance overlay.

/**
 * Indicates the origin of the advice.  The backend may return other
 * sources beyond the known set; unknown values are retained as-is.
 */
export type CoachSource = 'chart' | 'equity' | 'rule' | 'fallback' | (string & {});

/**
 * A single segment of the coach's suggested strategy bar.  Each entry
 * represents an action and the fraction of time that action should be
 * taken (0–1).  The UI will convert these into percentage widths.
 */
export interface StrategyPart {
  action: string;
  pct: number;
}

/**
 * The minimal coach advice payload expected by the frontend.  The
 * `bucket` identifies the recommended action (fold, call, raise_x.x, jam,
 * etc.).  The optional `strategy_bar` contains finer distribution data
 * that can be visualised.  A free‑form `rationale` may be provided for
 * explanatory text or tooltips.  The `raw` field preserves any extra
 * backend data for debugging.
 */
export interface CoachAdvice {
  source: CoachSource;
  bucket: string;
  strategy_bar?: StrategyPart[];
  rationale?: string;
  raw?: unknown;
}