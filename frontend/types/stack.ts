// frontend/types/stack.ts
// Shared stack / chip accounting types for the table, overlays and utilities.
//
// These are purely structural types – no game logic here. They are intended
// to be used by DecisionContext, stack helpers, and any components that need
// to reason about stacks or committed chips.

export type SeatIndex = number;

/** Backwards-compat alias used by helpers (e.g. utils/stack.ts). */
export type SeatId = SeatIndex;

/** Chip unit. All stack, pot and bet sizes are expressed in chips. */
export type Chips = number;

/** Remaining stack per seat (chips behind, *excluding* chips already in the pot). */
export type StackBySeat = Record<SeatIndex, Chips>;

/** Chips already committed to the current pot per seat. */
export type CommittedBySeat = Record<SeatIndex, Chips>;

/**
 * Hero-centric snapshot of stack state at the moment of a decision.
 *
 * This is a lightweight view used by DecisionContext and overlays; it does
 * not try to encode full game rules (side pots, etc.).
 */
export interface HeroStackSnapshot {
  /** Hero seat index. */
  heroSeat: SeatIndex;

  /** Hero's remaining stack (chips behind, not including committed). */
  heroStack: Chips;

  /** Chips hero has already committed to the current pot. */
  heroCommitted: Chips;

  /**
   * Effective stack size vs the main opponent in heads-up pots.
   * For multi-way spots this may be:
   *   - the minimum stack among active opponents, or
   *   - null if not computed.
   */
  effectiveStack: Chips | null;
}

/**
 * Optional richer multi-way stack view attached to a decision or hand state.
 *
 * Not all callers need this; you can attach it where convenient (e.g. when
 * building DecisionContext) and consume only the pieces you care about.
 */
export interface StackView {
  /** Remaining stack per seat (chips behind). */
  stacks: StackBySeat;

  /** Chips already committed to the current pot per seat. */
  committed?: CommittedBySeat;

  /** Hero-centric summary; may be omitted if hero context is unknown. */
  hero?: HeroStackSnapshot;
}

/**
 * Result of an effective stack computation for the acting hero.
 *
 * This mirrors the return type of computeEffectiveStack in utils/stack.ts.
 */
export interface EffectiveStackResult {
  heroSeat: SeatId;
  effectiveVsSeat: SeatId | null;
  effectiveStack: Chips | null;
}
