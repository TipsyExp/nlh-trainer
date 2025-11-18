// frontend/utils/range.ts
// Helpers to resolve villain ranges for preflop equity.
//
// The equity overlay needs a range for the villain when evaluating
// preflop situations.  Ideally this comes from the coach/chart
// metadata; however in Phase 3 we do not yet have chart integration.
// This helper consults build‑time environment variables to provide a
// fallback range.  When no range is configured the string 'random'
// will be returned if the backend supports it.

import type { DecisionContext } from '../types/decision';

export type RangeOrigin = 'chart' | 'default' | 'random';

/**
 * Attempt to resolve a villain range for the given decision context.
 * In this phase no chart metadata is available so we use the
 * NEXT_PUBLIC_EQUITY_DEFAULT_RANGE environment variable.  If it is
 * empty the string 'random' is returned when the backend can accept
 * the keyword (ompeval does).  If both fail, null is returned to
 * indicate that equity should be skipped.
 */
export function resolveVillainRange(
  _ctx: DecisionContext
): { range: string | null; origin: RangeOrigin } {
  const raw = process.env.NEXT_PUBLIC_EQUITY_DEFAULT_RANGE;
  if (raw && typeof raw === 'string' && raw.trim().length > 0) {
    return { range: raw.trim(), origin: 'default' };
  }
  // The backend supports 'random' as a keyword for uniformly random range
  return { range: 'random', origin: 'random' };
}
