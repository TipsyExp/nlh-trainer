// frontend/utils/stack.ts
// Helpers for stack handling and effective-stack calculations.
//
// This module centralises simple stack maths so that both the table
// UI and the guidance overlay can reason about "chips behind" and
// effective stack sizes in a consistent way.

import type {
  SeatId,
  Chips,
  StackBySeat,
  CommittedBySeat,
  EffectiveStackResult,
} from '../types/stack';

/**
 * Normalise an arbitrary numeric-ish value into a non-negative chip count.
 * Any NaN / negative / non-finite value is treated as 0.
 */
export function toChips(raw: unknown): Chips {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n;
}

/**
 * Return the hero's remaining stack (chips behind), given per-seat stacks
 * and optional committed amounts.
 *
 * By convention seatStacks should already be "behind" (remaining) stacks.
 * If you pass total stacks instead, you can subtract seatCommitted first.
 */
export function heroStackFromMaps(
  heroSeat: SeatId,
  seatStacks: StackBySeat | undefined,
  seatCommitted?: CommittedBySeat
): Chips | null {
  if (!seatStacks) return null;

  const raw = seatStacks[heroSeat];
  if (raw == null) return null;

  const committed = seatCommitted ? toChips(seatCommitted[heroSeat]) : 0;
  const remaining = toChips(raw) - committed;
  return remaining >= 0 ? remaining : 0;
}

/**
 * Compute an "effective stack" for the hero versus a main opponent.
 *
 * For each other seat with a positive stack, we compute:
 *
 *   eff(hero, villain) = min(hero_remaining, villain_remaining)
 *
 * and pick the villain seat that yields the largest eff. This is a
 * reasonable approximation of "effective stack vs the main opponent"
 * in heads-up and small multi-way pots.
 */
export function computeEffectiveStack(
  heroSeat: SeatId,
  seatStacks: StackBySeat | undefined,
  seatCommitted?: CommittedBySeat
): EffectiveStackResult {
  const stacks = seatStacks || {};

  const heroRemaining = heroStackFromMaps(heroSeat, stacks, seatCommitted) ?? 0;

  let bestSeat: SeatId | null = null;
  let bestEff: Chips | null = null;

  for (const [seatKey, rawStack] of Object.entries(stacks)) {
    const seat = Number(seatKey) as SeatId;
    if (seat === heroSeat) continue;

    const villainTotal = toChips(rawStack);
    const villainCommitted = seatCommitted
      ? toChips(seatCommitted[seat])
      : 0;
    const villainRemaining = Math.max(0, villainTotal - villainCommitted);

    const eff = Math.min(heroRemaining, villainRemaining);
    if (eff <= 0) continue;

    if (bestEff === null || eff > bestEff) {
      bestEff = eff;
      bestSeat = seat;
    }
  }

  return {
    heroSeat,
    effectiveVsSeat: bestSeat,
    effectiveStack: bestEff,
  };
}

/**
 * Lightweight formatter for displaying stack sizes in the UI.
 *
 * Example outputs:
 *   formatStack(7500)                 -> "7,500"
 *   formatStack(7500, 100)           -> "7,500 (75.0 BB)"
 *   formatStack(null, 100)           -> "—"
 */
export function formatStack(
  chips: Chips | null | undefined,
  bb?: Chips | null,
  precision: number = 1
): string {
  const n = toChips(chips ?? 0);
  if (chips == null || n === 0) {
    return '—';
  }

  const base = n.toLocaleString();

  if (!bb || bb <= 0) {
    return base;
  }

  const bbCount = n / bb;
  return `${base} (${bbCount.toFixed(precision)} BB)`;
}
