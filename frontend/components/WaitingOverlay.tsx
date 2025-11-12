// frontend/components/WaitingOverlay.tsx

/**
 * Simple overlay shown when the user must wait for the AI or other background work.
 *
 * This component is optional but helps provide a consistent waiting UX across
 * the application. When `show` is true it renders a full‑screen translucent
 * overlay with the provided message. When `show` is false it renders
 * nothing. You can import and use this in pages such as the table to signal
 * that bots are thinking in production mode.
 */
import React from "react";

export interface WaitingOverlayProps {
  /** Whether to display the overlay. */
  show: boolean;
  /** Optional message. Defaults to "Waiting for opponents…". */
  message?: string;
}

export function WaitingOverlay({ show, message }: WaitingOverlayProps) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="rounded-xl bg-white px-4 py-3 shadow-lg">
        <span className="text-sm font-medium text-gray-800">
          {message || "Waiting for opponents…"}
        </span>
      </div>
    </div>
  );
}

export default WaitingOverlay;