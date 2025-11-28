// frontend/utils/potSizing.ts
// Helpers for converting between pot-percentage labels (e.g. "33%")
// and numeric bet / raise totals in chips.
//
// This is deliberately UI-focused: the backend remains the authority on
// what actions are legal, and these helpers just compute reasonable
// totals that respect min / max bounds and hero's remaining stack.

import type { Chips } from "../types/stack";

/**
 * Parse a percentage label like "33%" or "75.5%" into a fraction in [0, 1].
 * Returns null if the label is not a simple percentage.
 */
export function parsePercentLabel(label: string): number | null {
  const m = String(label).trim().match(/^(\d+(?:\.\d+)?)%$/);
  if (!m) return null;

  const pct = Number(m[1]);
  if (!Number.isFinite(pct) || pct <= 0) return null;

  return pct / 100;
}

/**
 * Compute a total bet / raise amount for a pot-percentage label.
 *
 * Inputs:
 *  - label:     percentage bucket label, e.g. "33%", "50%", "75%", "100%".
 *  - potBefore: pot size in chips before hero acts (P).
 *  - toCall:    chips hero must call to continue (C). This is 0 for
 *               pure bet spots and >0 for facing a bet / raise.
 *  - minTotal:  optional minimum legal total (e.g. min-raise total).
 *  - maxTotal:  optional maximum legal total (e.g. jam total from backend).
 *  - heroStack: optional remaining chips behind for hero (excluding
 *               any chips already committed).
 *
 * Formula (from the design doc):
 *
 *   pot_after_call = P + C
 *   total_invested = C + X * pot_after_call
 *
 * where X is the fraction corresponding to the percentage (e.g. 0.5
 * for "50%"). We then clamp this total to legal bounds and hero's
 * remaining stack and round to the nearest whole chip.
 */
export function amountForPercentLabel(
  label: string,
  potBefore: Chips,
  toCall: Chips,
  minTotal?: Chips | null,
  maxTotal?: Chips | null,
  heroStack?: Chips | null
): Chips {
  const frac = parsePercentLabel(label);
  const pot = Number(potBefore) || 0;
  const call = Number(toCall) || 0;

  // Fallback: if the label is not a percent, just return a safe minimum.
  if (!frac) {
    const fallback =
      minTotal != null && minTotal > 0 ? Number(minTotal) : call;
    const n = Math.round(fallback);
    return n > 0 ? n : 0;
  }

  const potAfterCall = pot + call;
  let total = call + frac * potAfterCall;

  // Clamp to explicit max bound if provided (e.g. jam total).
  if (typeof maxTotal === "number" && maxTotal > 0) {
    total = Math.min(total, maxTotal);
  }

  // Clamp so that the *additional* chips do not exceed hero's stack.
  if (typeof heroStack === "number" && heroStack >= 0) {
    const maxByStack = call + heroStack;
    total = Math.min(total, maxByStack);
  }

  // Enforce minimum total (e.g. min-raise) or at least a call.
  const min =
    minTotal != null && minTotal > 0 ? Number(minTotal) : call;
  if (total < min) {
    total = min;
  }

  const rounded = Math.round(total);
  return rounded > 0 ? rounded : 0;
}

/**
 * Quick guard: does this bucket look like a plain "X%" percentage?
 */
export function isPercentBucket(label: string): boolean {
  return /^(\d+(?:\.\d+)?)%$/.test(String(label).trim());
}

/**
 * Given a total bet / raise amount, infer the approximate percentage
 * of pot it represents, as a fractional value in [0, 1]. This can be
 * useful when the backend provides numeric sizes and the UI wants to
 * display them as percentages.
 *
 * Returns null if the pot is degenerate.
 */
export function impliedPercentFromTotal(
  total: Chips,
  potBefore: Chips,
  toCall: Chips
): number | null {
  const pot = Number(potBefore) || 0;
  const call = Number(toCall) || 0;
  const t = Number(total) || 0;

  const potAfterCall = pot + call;
  if (potAfterCall <= 0) return null;

  const extra = t - call;
  if (extra <= 0) return 0;

  const frac = extra / potAfterCall;
  if (!Number.isFinite(frac) || frac < 0) return null;

  return frac;
}

/**
 * Convenience formatter to turn an implied fraction back into a
 * "33%" style label for display.
 */
export function formatPercent(
  frac: number | null | undefined,
  precision: number = 0
): string {
  if (frac == null || !Number.isFinite(frac) || frac < 0) {
    return "—";
  }
  return `${(frac * 100).toFixed(precision)}%`;
}
