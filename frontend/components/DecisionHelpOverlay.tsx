// frontend/components/DecisionHelpOverlay.tsx
// Presentational overlay for hand guidance (phase 1 only).
//
// This component renders a fixed panel on the right side of the screen (or
// bottom on small screens) with placeholder sections for preflop advice and
// equity.  In Phase 1 it contains no side effects and does not fetch any
// data.  The overlay is gated by environment flags and a per‑session toggle.

import React from "react";

export interface DecisionHelpOverlayProps {
  /** Optional decision context that will be used in later phases. */
  decision?: any;
}

export function DecisionHelpOverlay({ decision }: DecisionHelpOverlayProps) {
  // Phase 1: ignore decision; just render shell.
  return (
    <div
      role="region"
      aria-label="Guidance"
      className="fixed z-40 right-4 top-4 md:right-4 md:top-4 max-w-[90vw] w-80 md:w-96"
    >
      <div className="bg-white shadow-lg rounded-xl p-4 space-y-3">
        <h2 className="text-lg font-semibold">Guidance</h2>
        <div className="space-y-3 text-sm">
          <div>
            <h3 className="font-medium">Preflop advice</h3>
            <p className="text-gray-500">
              Guidance will appear here in a later phase.
            </p>
          </div>
          <div>
            <h3 className="font-medium">Equity</h3>
            <p className="text-gray-500">
              Equity information will appear here in a later phase.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DecisionHelpOverlay;