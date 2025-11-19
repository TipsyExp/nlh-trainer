// frontend/store/overlayDebugStore.ts
// Simple in‑memory store to trace overlay calls during Phase 4.
//
// Snapshot‑aware testing requires the frontend to know whether the
// overlay invoked the coach and equity endpoints for the current
// decision.  This module stores the most recent call information so
// that a dev inspector can display it.  It uses a basic publish/
// subscribe pattern to notify subscribers when the trace changes.

export interface OverlayTrace {
  /** The current hand identifier. */
  handId: string | null;
  /** The zero‑based decision index. */
  idx: number | null;
  /** Current street (preflop/flop/turn/river/showdown/unknown). */
  street: string | null;
  /** Whether the overlay made a coach request for this decision. */
  calledCoach: boolean;
  /** Whether the overlay made an equity request for this decision. */
  calledEquity: boolean;
}

// Internal mutable state.
let trace: OverlayTrace = {
  handId: null,
  idx: null,
  street: null,
  calledCoach: false,
  calledEquity: false,
};

// Listeners subscribed to trace updates.
const listeners: Array<(t: OverlayTrace) => void> = [];

/**
 * Get the current overlay trace.  Returns a shallow copy to prevent
 * accidental mutation.
 */
export function getOverlayTrace(): OverlayTrace {
  return { ...trace };
}

/**
 * Set the current overlay trace.  Notifies all subscribers with the
 * updated trace.  Partial updates are merged into the existing trace.
 *
 * @param newTrace Partial or full trace to assign.
 */
export function setOverlayTrace(newTrace: Partial<OverlayTrace>): void {
  trace = { ...trace, ...newTrace };
  for (const fn of listeners) {
    try {
      fn(getOverlayTrace());
    } catch {
      // ignore subscriber errors
    }
  }
}

/**
 * Subscribe to trace updates.  The callback will be invoked
 * immediately with the current trace and subsequently whenever
 * setOverlayTrace is called.  Returns an unsubscribe function.
 */
export function subscribeOverlayTrace(fn: (t: OverlayTrace) => void): () => void {
  listeners.push(fn);
  // Invoke immediately so subscriber sees current state.
  fn(getOverlayTrace());
  return () => {
    const idx = listeners.indexOf(fn);
    if (idx >= 0) listeners.splice(idx, 1);
  };
}

/**
 * Reset the overlay trace to its initial state.  Intended for tests.
 */
export function resetOverlayTrace(): void {
  trace = {
    handId: null,
    idx: null,
    street: null,
    calledCoach: false,
    calledEquity: false,
  };
  for (const fn of listeners) {
    try {
      fn(getOverlayTrace());
    } catch {
      /* noop */
    }
  }
}