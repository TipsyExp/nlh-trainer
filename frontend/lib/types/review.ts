// frontend/lib/types/review.ts

// --- Shared primitives ---

export type Street = "preflop" | "flop" | "turn" | "river";
export type Card = string; // e.g., "Ah", "Kd", "3s"

export type StrategyMap = Record<string, number>;
export type EVMap = Record<string, number>;

// --- Coach advice snapshot (backend parity) ---

export interface AdviceSnapshot {
  recommended_bucket: string;
  strategy: StrategyMap;  // e.g., {"check":0.2,"50%":0.5,"100%":0.3}
  ev_map: EVMap;          // e.g., {"check":-0.05,"50%":0.12,"100%":0.15}
  meta?: {
    status?: string;      // "ok" | "disabled" | "unsupported" | "timeout" | "error"
    cached?: boolean;
    latency_ms?: number;
    node_key?: string | null;
  };
}

// Alias used by some components
export type CoachAdviceSnapshot = AdviceSnapshot;

// --- List (GET /api/review/hands) ---

// Your original list item
export interface ReviewHandListItem {
  hand_id: string;
  finished_at: string | null; // ISO or null if in-progress
  seats: number;
  final_pot: number | null;
  winners: string[];          // display labels as provided
  action_count: number;
  has_advice: boolean;
}

export interface GetReviewHandsResponse {
  hands: ReviewHandListItem[];
  meta?: {
    limit?: number;
    count?: number;
  };
}

// UI-friendly list item used by ReviewListTable (flatten and add a couple fields)
// Keep both in M1; server can return either and the page can adapt.
export interface ReviewListItem {
  hand_id: string;
  finished: boolean;                  // derived from finished_at != null
  seats: number;
  final_pot: number | null;
  winners: string;                    // compact string summary for table
  action_count: number;               // same as action_count above
  has_advice: boolean;
  started_at?: string | null;
  finished_at?: string | null;
}

// --- Detail (GET /api/review/hand/{hand_id}) ---

// Board representation (array form; turn/river may be [] or omitted)
export interface BoardState {
  flop?: Card[];    // length 3 when present
  turn?: Card[];    // length 1 when present
  river?: Card[];   // length 1 when present
}

// Original action row from your earlier spec
export interface ActionRow {
  idx: number;                               // 0-based decision index
  street?: Street;                           // if available
  actor: string;                             // player label/seat
  action: string;                            // "bet" | "call" | "check" | "fold" | "raise" | etc.
  amount?: number | null;
  pot_after?: number | null;
  stacks_after?: Record<string, number> | null;
  timestamp?: string | null;                 // ISO if recorded
  notes?: string | null;                     // optional freeform/debug info
}

// Alias used by ActionPanel and other components
export type ReviewAction = ActionRow;

export interface HandSummary {
  seats: number;
  final_pot: number | null;
  winners: string[];           // full list for details page
  started_at?: string | null;  // ISO
  finished_at?: string | null; // ISO
}

// Full response in your earlier shape
export interface GetReviewHandResponse {
  hand_id: string;
  summary: HandSummary;
  board?: BoardState;
  actions: ActionRow[];
  // string keys in JSON (server) — treat as number indices in UI
  advice_by_idx: Record<string, AdviceSnapshot>;
}

// UI-friendly flattened detail used by /review/[hand_id].tsx
export interface ReviewHandDetail {
  hand_id: string;
  finished: boolean;
  seats: number;
  final_pot: number | null;
  winners: string[];
  actions: ReviewAction[];
  advice_by_idx: Record<number, CoachAdviceSnapshot>;
  board?: BoardState;
  started_at?: string | null;
  finished_at?: string | null;
}
