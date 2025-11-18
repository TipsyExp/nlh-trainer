// frontend/types/decision.ts
// Stub types for decision context used by the guidance overlay.
//
// In later phases this will be extended to include more detail about the
// current game state (street, hero hand, villain range, etc.).  For now
// it's included so that components can accept a typed `decision` prop
// without importing poker state types.

export interface DecisionContext {
  handId: string | null;
  idx: number | null;
  street: string | null;
  heroSeat: number;
  pot: number;
  toCall: number;
}