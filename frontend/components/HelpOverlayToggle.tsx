// frontend/components/HelpOverlayToggle.tsx
// A small on/off toggle for the hand guidance overlay.
//
// The toggle manages only the per‑session enabled state.  It does not
// consider the global gate; callers are expected to wrap this component in a
// check against the globalOverlayGate.  It forwards the enabled state and
// setter via props.

import React from "react";

export interface HelpOverlayToggleProps {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

export function HelpOverlayToggle({
  enabled,
  setEnabled,
}: HelpOverlayToggleProps) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
      <input
        type="checkbox"
        className="accent-black"
        checked={enabled}
        onChange={(e) => setEnabled(e.target.checked)}
      />
      <span>Show guidance</span>
    </label>
  );
}

export default HelpOverlayToggle;