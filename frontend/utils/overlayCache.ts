// frontend/utils/overlayCache.ts
// Simple in-memory cache for the guidance overlay.
//
// The overlay caches *unified* coach advice responses keyed by hand_id and
// decision index to avoid duplicate requests when the user re-renders or
// revisits the same decision. It also maintains an in-flight map so that
// concurrent requests for the same key can share a single promise rather
// than producing parallel network traffic. Negative cache entries are
// stored alongside positive ones to avoid repeated calls for disabled,
// unsupported, or missing endpoints.

import type { Advice } from '../types/advice';

/**
 * UI-level status for a coach response.
 *
 * This is *not* a field on the backend AdvicePayloadV1 — it's how the
 * overlay classifies the result of attempting to fetch advice:
 *
 *  - "ok":         HTTP 200, parsed Advice payload.
 *  - "disabled":   backend route returns 501 / explicitly disabled.
 *  - "not_found":  404, or hand/idx missing.
 *  - "unavailable": network error, timeout, or other fetch failure.
 */
export type CoachStatus = 'ok' | 'disabled' | 'not_found' | 'unavailable';

/**
 * Normalised response record used internally by the overlay.
 * When `status === "ok"` the `data` field contains the unified advice
 * payload. For other statuses `data` will be null and `error` may contain
 * a user-friendly message.
 */
export interface CoachResponse {
  data: Advice | null;
  status: CoachStatus;
  error?: string;
}

const coachCache: Map<string, CoachResponse> = new Map();
const coachInFlight: Map<string, Promise<CoachResponse>> = new Map();

export function getCoach(key: string): CoachResponse | undefined {
  return coachCache.get(key);
}

export function setCoach(key: string, response: CoachResponse): void {
  coachCache.set(key, response);
}

export function getCoachInFlight(key: string): Promise<CoachResponse> | undefined {
  return coachInFlight.get(key);
}

export function setCoachInFlight(key: string, promise: Promise<CoachResponse>): void {
  coachInFlight.set(key, promise);
}

export function deleteCoachInFlight(key: string): void {
  coachInFlight.delete(key);
}

/** Remove all cached coach values. Primarily used for testing. */
export function clearCoachCaches(): void {
  coachCache.clear();
  coachInFlight.clear();
}

// -----------------------------------------------------------------------------
// NOTE: Equity caching
//
// Previously the overlay used a separate cache layer for `/api/equity`
// responses (EquityResponse / EquityStatus, etc.).
//
// With the unified `/api/coach/advice` endpoint, equity is now bundled
// directly into the advice payload (Advice.equity), so we no longer
// maintain a separate equity cache here. All callers should rely on the
// single CoachResponse cache above.
