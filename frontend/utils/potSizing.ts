// frontend/utils/potSizing.ts
// Helpers for converting between pot-percentage labels (e.g. "33%")
// and numeric bet / raise totals in chips.
//
// This is deliberately UI-focused: the backend remains the authority on
// what actions are legal, and these helpers just compute reasonable
// totals that respect hero's remaining stack and any explicit max
// (e.g. jam). We intentionally DO NOT hard-enforce min-raise here so
// that the displayed percentages stay intuitive; the engine will still
// snap / reject illegal sizes if needed.

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
 *  - pot:       pot size in chips before hero acts (P).
 *  - toCall:    chips hero must call to continue (C). This is 0 for
 *               pure bet spots and >0 for facing a bet / raise.
 *  - heroStack: remaining chips behind for hero (excluding any chips
 *               already committed). This is used to ensure we never propose
 *               a total greater than the hero’s stack.
 *  - minRaise:  optional advertised minimum legal total (e.g. min-raise
 *               total). **Currently treated as informational only** so
 *               that displayed pot-percentages remain intuitive.
 *  - maxRaise:  optional maximum legal total (e.g. jam total from backend).
 *
 * Formula (UI side):
 *   total = C + f * (P + C)
 * where f is the fraction corresponding to the percentage. We then clamp
 * this total to hero's remaining stack and any explicit max bound, and
 * round to the nearest whole chip. If the result is <= 0, returns null.
 */
export function amountForPercentLabel(
  label: string,
  pot: Chips,
  toCall: Chips,
  heroStack: Chips,
  minRaise?: Chips, // kept for signature compatibility; not enforced
  maxRaise?: Chips
): Chips | null {
  const frac = parsePercentLabel(label);
  if (frac == null) return null;

  const P = Number(pot) || 0;
  const C = Number(toCall) || 0;

  // Base pot-percentage sizing: fraction of (pot + amount to call),
  // added on top of the call amount.
  let total = C + frac * (P + C);

  // NOTE: we intentionally do NOT clamp up to minRaise here. Doing so
  // would make intuitive labels like "50%" drift to odd values (e.g.
  // 350 into a 500 pot when min-raise happens to be large). The engine
  // remains the authority on legality and will snap / reject out-of-line
  // sizes as needed.

  // Clamp to explicit max bound if provided (e.g. jam total).
  if (typeof maxRaise === "number" && maxRaise > 0 && total > maxRaise) {
    total = maxRaise;
  }

  // Clamp so that the *additional* chips do not exceed hero's stack. If
  // heroStack is undefined we skip this check and rely on other bounds.
  if (typeof heroStack === "number" && heroStack >= 0) {
    const maxByStack = C + heroStack;
    if (total > maxByStack) {
      total = maxByStack;
    }
  }

  const rounded = Math.round(total);
  return rounded > 0 ? rounded : null;
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
