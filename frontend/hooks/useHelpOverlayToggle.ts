// frontend/hooks/useHelpOverlayToggle.ts
// Hook to manage a per‑session guidance overlay toggle.
//
// This hook reads and writes a value in localStorage keyed by
// `helpOverlay:<sessionId>`.  When no entry is present the default is
// `true` so that the overlay starts enabled when permitted by the global
// gate.  Callers should combine this with `globalOverlayGate` to decide
// whether to actually mount the overlay.

import { useState, useEffect } from "react";

export function useHelpOverlayToggle(sessionId?: string) {
  // Derive a unique key per session; fall back to a generic key when
  // sessionId is unknown.
  const key = `helpOverlay:${sessionId ?? "default"}`;

  const [enabled, setEnabled] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null) {
        // Default to true for a new session.
        return true;
      }
      return raw === "1" || raw === "true";
    } catch {
      return true;
    }
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(key, enabled ? "1" : "0");
    } catch {
      // Ignore storage errors (e.g. quota exceeded).
    }
  }, [key, enabled]);

  return { enabled, setEnabled };
}

export default useHelpOverlayToggle;