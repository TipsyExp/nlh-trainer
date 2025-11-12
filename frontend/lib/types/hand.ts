// Updated HandState and related types for the NLH Trainer frontend.
// This file mirrors the original types from the repository but clarifies
// that the frontend should rely on server-provided fields for turn,
// allowed actions, pot totals, and last-action details. It also adds
// a typed shape for the last action with an optional committed amount.

// Define the possible actions a player can take.
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
 * `amount` field may indicate the total chip count required.
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
 * A typed representation of the most recent action in the hand. The
 * backend may include the seat, action kind, and an amount. When a
 * player calls, the `committed` field contains the total chips put in
 * by that call; for a bet/raise/jam the amount may reflect the new
 * total bet. Extra keys from the backend are allowed to ensure
 * forwards‑compatibility.
 */
export interface LastAction {
  seat: number;
  action: ActionKind | string;
  committed?: number;
  amount?: number;
  [key: string]: any;
}

export type HandState = {
  table: TableShape;
  players: PlayerPublic[];
  street: string;
  deck_seed?: string | null;
  /** The last action that occurred in this hand. */
  last_action?: LastAction;
  /**
   * Stable, cumulative pot size. Always use this field rather than
   * calculating pot from bets.
   */
  pot_total?: number;
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