// frontend/lib/types/hand.ts
// Updated HandState and related types for the NLH Trainer frontend.
// This file mirrors the original types from the repository but clarifies
// that the frontend should rely on server-provided fields for turn,
// allowed actions, pot totals, last-action details, and board structure.

/** Define the possible actions a player can take. */
export type ActionKind =
  | "fold"
  | "check"
  | "call"
  | "bet"
  | "raise"
  | "jam";

/**
 * A single allowed action entry. The backend may return a list of these
 * instead of simple bucket strings. For bet/raise/jam actions the
 * `amount` field may indicate the TOTAL chip count required.
 */
export type AllowedAction = {
  type: ActionKind;
  amount?: number;
};

/**
 * The context for a player's turn describing call amount, minimum raise,
 * and the set of allowed buckets. The UI should use this to decide
 * which buttons to render. The backend may also return a richer
 * `actions` array; if present, prefer it for constructing action
 * requests.
 */
export type AllowedContext = {
  to_call: number;
  min_raise: number;
  allowed_buckets: string[];
  actions?: AllowedAction[];
};

export type PlayerPublic = {
  seat: number;
  hole_cards: [string, string] | string[];
};

export type TableShape = {
  seats: number;
  sb: number;
  bb: number;
  ante: number;
  button: number;
  sb_seat: number;
  bb_seat: number;
};

/**
 * A typed representation of the most recent action in the hand.
 *
 * The backend's public state (via `_la_to_dict` in backend/api/hand.py)
 * exposes:
 *   seat, type, requested, committed, snapped, bucket_label, allowed_buckets
 *
 * `type` is the canonical field; `action` is kept as a soft alias for any
 * older callers that might still look for it.
 */
export interface LastAction {
  seat: number;

  /** Canonical backend key (`type` from _la_to_dict). */
  type?: ActionKind | string;

  /** Optional alias for compatibility with older UI code. */
  action?: ActionKind | string;

  requested?: number;
  committed?: number;
  snapped?: boolean;
  bucket_label?: string;
  allowed_buckets?: string[];

  [key: string]: any;
}

/**
 * Public hand state as returned by GET /api/hand/state.
 *
 * The frontend should treat this as the source of truth for:
 *   - table configuration (blinds, seats, button),
 *   - hero/opponent hole cards (with masking for opponents),
 *   - street and board,
 *   - pot_total,
 *   - whose turn it is (`to_act`) and allowed actions (`allowed`),
 *   - last_action metadata.
 */
export type HandState = {
  table: TableShape;
  players: PlayerPublic[];
  street: string;
  deck_seed?: string | null;

  /** Board cards as provided by backend.api.hand._to_public_state. */
  board?: {
    flop: string[];
    turn: string[];
    river: string[];
    // Future-proofing for any additional board views.
    [key: string]: string[] | undefined;
  };

  /** The last action that occurred in this hand. */
  last_action?: LastAction;

  /**
   * Stable, cumulative pot size. Always use this field rather than
   * calculating pot from bets.
   */
  pot_total?: number;

  /**
   * Optional per-seat remaining stack maps (if backend chooses to expose them).
   * These are not required by the UI but are helpful for overlays and
   * effective-stack calculations.
   */
  stacks_by_seat?: Record<number, number>;
  committed_by_seat?: Record<number, number>;

  /**
   * The seat index whose turn it currently is. If null, no one can act
   * (for example, the hand may be finished or waiting on bots).
   */
  to_act?: number | null;

  /**
   * The allowed actions for the current actor. The frontend should use
   * this to determine which UI elements to enable.
   */
  allowed?: AllowedContext;

  /**
   * Legacy alias used by older UIs. Prefer `allowed`. Included for
   * backwards compatibility.
   */
  allowed_actions?: AllowedAction[];

  [key: string]: any;
};

export type Actor = {
  seat: number;
  to_call: number;
  allowed_buckets: string[];
  min_raise?: number;
};

export type StateResponse = {
  state: HandState;
  actor?: Actor | null;
  hand_id?: string;
  idx?: number;
};

export type ActionResponse = {
  ok: boolean;
  bots_applied: Array<{ seat: number; action: string; amount?: number }>;
  state: HandState;
  hand_id?: string;
  idx?: number;
};

export type SessionResponse = {
  ok: boolean;
  detail: string;
  session_id: number;
};
