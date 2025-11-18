// frontend/types/export.ts
// Types representing the export format returned by the backend snapshot API.
//
// Phase 4 introduces snapshot‑aware testing in the frontend.  When the
// overlay invokes the coach or equity endpoints with logging enabled,
// the backend persists snapshots of those calls.  The snapshots can
// then be retrieved via GET /api/export/hand/{hand_id}.json to verify
// that advice and equity were captured for a specific decision.
//
// This file defines minimal interfaces for the exported hand so that
// the dev inspector can inspect the presence of advice and equity
// snapshots without needing to know their full structure.  The actual
// contents of preflop_advice and equity_snapshot are opaque to the
// frontend; only the fact that they exist is asserted in tests.

export interface ExportDecision {
  /** Zero‑based decision index in the hand. */
  idx: number;
  /** Optional snapshot of preflop advice returned by the coach. */
  preflop_advice?: unknown;
  /** Optional snapshot of equity returned by the equity service. */
  equity_snapshot?: unknown;
}

export interface ExportHand {
  /** Identifier of the hand for which snapshots are exported. */
  hand_id: string;
  /** List of decisions in chronological order. */
  decisions: ExportDecision[];
}