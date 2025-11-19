// frontend/utils/export.ts
// Thin client for retrieving exported hand snapshots from the backend.
//
// Phase 4 adds snapshot‑aware testing by logging coach and equity
// requests when runtime flags are enabled.  The backend exposes
// snapshots via GET /api/export/hand/{hand_id}.json.  This helper
// function wraps that endpoint and returns the parsed JSON.  It uses
// the existing getJson helper from utils/http to ensure consistent
// timeout and abort semantics.

import { getJson } from './http';
import type { ExportHand } from '../types/export';

// Default client timeout for exporting a hand (in milliseconds).
// Exports are typically small JSON payloads and should return quickly.
const DEFAULT_EXPORT_TIMEOUT_MS = 2000;

/**
 * Fetch the exported snapshots for a given hand.  Returns the
 * entire export object which contains a list of decisions.  If the
 * request fails or times out, the promise rejects.  A caller may
 * provide an AbortSignal to cancel the request prematurely.
 *
 * @param handId Hand identifier returned by the backend.
 * @param opts Optional timeout override and abort signal.
 */
export async function getHandExport(
  handId: string,
  opts?: { timeoutMs?: number; signal?: AbortSignal }
): Promise<ExportHand> {
  const timeoutMs = opts?.timeoutMs ?? DEFAULT_EXPORT_TIMEOUT_MS;
  const signal = opts?.signal;
  // Encode handId to avoid path traversal or special characters.
  const encoded = encodeURIComponent(handId);
  const res = await getJson(
    `/api/export/hand/${encoded}.json`,
    { timeoutMs, signal }
  );
  if (res.status === 'timeout') {
    throw new Error('Export request timed out');
  }
  if (!res.ok) {
    throw new Error(`Export failed (${res.status})`);
  }
  // The body should match ExportHand.
  return res.body as ExportHand;
}