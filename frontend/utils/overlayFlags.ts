// frontend/utils/overlayFlags.ts
// Global gate for the guidance overlay.
//
// The overlay should only mount when both NEXT_PUBLIC_DEV_TOOLS and
// NEXT_PUBLIC_HELP_OVERLAY_ENABLED environment variables are truthy.
// Truthy values include "1", "true", "yes", and "on" (case‑insensitive).

const toBool = (val: any): boolean => {
  return ["1", "true", "yes", "on"].includes(String(val).toLowerCase());
};

export const globalOverlayGate =
  toBool(process.env.NEXT_PUBLIC_DEV_TOOLS) &&
  toBool(process.env.NEXT_PUBLIC_HELP_OVERLAY_ENABLED);