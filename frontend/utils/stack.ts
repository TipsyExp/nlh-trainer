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
 * Extract a player's remaining stack (chips behind) from the public hand
 * state. The backend does not currently expose a single canonical field
 * for chips behind, so we check a few candidate fields on the player
 * object before falling back to any per-seat maps on the state. If none
 * are present or numeric, null is returned.
 *
 * Ordering of checks:
 *   1. player.stack – canonical chips behind on many backends.
 *   2. player.chips – alternative naming used by some adapters.
 *   3. player.stack_after – legacy fallback from older UIs.
 *   4. player.stack_behind – explicit naming if present.
 *   5. player.stack_chips – extremely old naming.
 *   6. seat-level maps on the state or table (stack_by_seat,
 *      stacks_by_seat, stacks_after, stacks, table.stacks, etc.).
 *
 * @param player Player object from state.players array.
 * @param state  Current hand state; may include seat-level stack maps.
 * @returns      Numeric chips behind or null if unknown.
 */
export function getPlayerStackFromState(
  player: any | null | undefined,
  state: any | null | undefined
): Chips | null {
  if (!player) return null;
  // Candidate fields on the player itself.
  const candidateFields = [
    'stack',
    'chips',
    'stack_after',
    'stack_behind',
    'stack_chips',
  ];
  for (const field of candidateFields) {
    const raw = (player as any)[field];
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return raw;
    }
  }
  // Fallback to any per-seat stack maps on the state. These maps may
  // include remaining stacks keyed by seat index. We check a few
  // commonly used names but gracefully ignore anything non-numeric.
  const seat = (player as any).seat;
  if (state && seat != null) {
    const maps = [
      (state as any).stack_by_seat,
      (state as any).stacks_by_seat,
      (state as any).stacks_after,
      (state as any).stacks,
      (state as any).table?.stacks,
      (state as any).table?.stacks_after,
      (state as any).table?.stack_by_seat,
      (state as any).table?.stacks_by_seat,
    ];
    for (const m of maps) {
      if (m && typeof m[seat] === 'number' && Number.isFinite(m[seat])) {
        return m[seat] as number;
      }
    }
  }
  return null;
}

/**
 * Return the hero's remaining stack (chips behind), given per-seat stacks.
 *
 * IMPORTANT: By convention `seatStacks` is already "behind" (remaining)
 * stack per seat (i.e. total stack minus any chips already committed to
 * the pot). In that case we do NOT subtract `seatCommitted` again.
 *
 * If you are working with TOTAL stacks instead, you should pre-adjust
 * them before calling this helper, e.g.:
 *
 *   const behind = totalStacks[seat] - committed[seat];
 *   heroStackFromMaps(heroSeat, { [seat]: behind });
 */
export function heroStackFromMaps(
  heroSeat: SeatId,
  seatStacks: StackBySeat | undefined,
  // Kept for signature compatibility but not used when stacks are already "behind".
  seatCommitted?: CommittedBySeat
): Chips | null {
  if (!seatStacks) return null;
  const raw = seatStacks[heroSeat];
  if (raw == null) return null;
  // seatStacks is defined as "remaining / behind" – just normalise.
  const remaining = toChips(raw);
  return remaining >= 0 ? remaining : 0;
}

/**
 * Compute an "effective stack" for the hero versus a main opponent.
 *
 * Assumes `seatStacks` is remaining stack (chips behind) per seat. For
 * each other seat with a positive remaining stack, we compute:
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
  // Kept for signature compatibility; not required when stacks are already "behind".
  seatCommitted?: CommittedBySeat
): EffectiveStackResult {
  const stacks = seatStacks || {};
  const heroRemaining = heroStackFromMaps(heroSeat, stacks, seatCommitted) ?? 0;

  let bestSeat: SeatId | null = null;
  let bestEff: Chips | null = null;

  for (const [seatKey, rawStack] of Object.entries(stacks)) {
    const seat = Number(seatKey) as SeatId;
    if (seat === heroSeat) continue;
    const villainRemaining = toChips(rawStack);
    if (villainRemaining <= 0) continue;
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
