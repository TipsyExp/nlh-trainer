// frontend/lib/types/hand.ts

export type ActionKind = "fold" | "check" | "call" | "bet" | "raise" | "jam";

export type AllowedAction = {
  type: ActionKind;
  amount?: number; // required for bet/raise/jam in some engines
};

export type AllowedContext = {
  to_call: number;
  min_raise: number;
  allowed_buckets: string[]; // e.g. ["call","2.2x","2.5x","3.0x","jam"]
  /** Optional richer list of typed actions if backend ever provides it */
  actions?: AllowedAction[];
};

export type PlayerPublic = {
  seat: number;
  hole_cards: [string, string] | string[]; // human: real; bots: ["XX","XX"]
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

export type HandState = {
  table: TableShape;
  players: PlayerPublic[];
  street: string; // "preflop" | "flop" | "turn" | "river" | "showdown"
  deck_seed?: string | null;
  last_action?: any;

  // New/important:
  pot_total?: number; // stable, cumulative pot (never resets per street)
  to_act?: number | null; // seat index whose turn it is
  allowed?: AllowedContext;

  /** Optional legacy alias some UIs used before `allowed` existed */
  allowed_actions?: AllowedAction[];

  // Keep room for any engine-specific extras
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
  actor?: Actor | null; // kept for backwards-compat; prefer state.to_act + state.allowed
  hand_id?: string;
  idx?: number;
};

export type ActionResponse = {
  ok: boolean;
  bots_applied: Array<Record<string, any>>;
  state: HandState;
  hand_id?: string;
  idx?: number;
};

export type SessionResponse = {
  ok: boolean;
  detail: string;
  session_id: number;
};
