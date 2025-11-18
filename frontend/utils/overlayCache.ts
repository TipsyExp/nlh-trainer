// frontend/utils/overlayCache.ts
// Simple in-memory caches for the guidance overlay.
//
// The overlay should cache coach responses keyed by hand_id and
// decision index to avoid duplicate requests when the user re-renders
// or revisits the same decision.  It also maintains an in-flight map
// so that concurrent requests for the same key can share a single
// promise rather than producing parallel network traffic.  Negative
// cache entries are stored alongside positive ones to avoid repeated
// calls for disabled or missing endpoints.

import type { CoachAdvice } from '../types/coach';

/**
 * Enumerated statuses for coach responses.  `ok` indicates a normal
 * result; `disabled` corresponds to HTTP 501 from the backend,
 * `not_found` corresponds to HTTP 404, and `unavailable` denotes
 * timeouts or other network failures.
 */
export type CoachStatus = 'ok' | 'disabled' | 'not_found' | 'unavailable';

/**
 * A normalised response record used internally by the overlay.  When
 * `status` is `ok` the `data` field contains the coach advice.  For
 * other statuses `data` will be null and `error` may contain a
 * user‑friendly message.
 */
export interface CoachResponse {
  data: CoachAdvice | null;
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

/** Remove all cached values.  Primarily used for testing. */
export function clearCoachCaches(): void {
  coachCache.clear();
  coachInFlight.clear();
}