// frontend/types/decision.ts
// Decision context used by the guidance overlay (Phase 3).
//
// The DecisionContext aggregates the minimum information about the
// current hand required by the guidance overlay to fetch coach advice
// and compute equity. It includes identifiers, street, hero cards,
// board cards, known opponent hands and player counts.
//
// Newer iterations also add optional stack-related fields so that
// solver-backed advice and pot-percentage sizing can reason about
// effective stacks.

import type {
  Chips,
  StackBySeat,
  CommittedBySeat,
} from './stack';

export interface DecisionContext {
  /** The current hand identifier, null when unknown. */
  handId: string | null;
  /** Decision index within the hand; null when not acting. */
  idx: number | null;
  /** Street name (preflop, flop, turn, river, showdown), null when unknown. */
  street: string | null;
  /** Seat index for the hero (0-based). */
  heroSeat: number;
  /** Total chips in the pot prior to acting. */
  pot: number;
  /** Chips required to call. */
  toCall: number;
  /**
   * The hero's hole cards. Always two strings when available; when
   * unknown or masked (e.g. during preflop when cards haven't been
   * dealt) this may be an empty array or contain placeholders.
   */
  heroCards: string[];
  /**
   * Flattened board cards across all streets. May be shorter than 5
   * during flop/turn. Empty when preflop.
   */
  board: string[];
  /**
   * A mapping of seat to that player's known hole cards. Only
   * includes opponents with fully revealed hands (e.g. at showdown).
   */
  knownHandsBySeat: Record<number, string[]>;
  /**
   * The number of live players in the hand. Used to gate postflop
   * equity based on backend limitations. In Phase 3 this is derived
   * from the table state and may be capped by meta.equity.max_players.
   */
  playerCount: number;
  /** Maximum number of players supported by the backend; passed down from meta. */
  maxPlayers?: number;

  // ---- Optional stack fields (new) ---------------------------------------

  /**
   * Hero's remaining stack in chips (behind, excluding chips already
   * committed to the current pot). Optional while stack wiring is
   * being rolled out.
   */
  heroStack?: Chips | null;

  /**
   * Effective stack size vs the main opponent in heads-up pots. For
   * multi-way spots or when not computed, this may be null or omitted.
   */
  effectiveStack?: Chips | null;

  /** Remaining stack per seat (chips behind). */
  stackBySeat?: StackBySeat;

  /** Chips already committed to the current pot per seat. */
  committedBySeat?: CommittedBySeat;
}
