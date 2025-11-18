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

// -----------------------------------------------------------------------------
// Equity caching
//
// Similar to the coach cache, the equity overlay caches results by
// (hand_id, idx, street and signature) to avoid duplicate POST calls.  A
// separate in‑flight map stores active Promises so that concurrent
// requests share the same network call.  Negative entries are stored
// alongside successful results so that repeated visits to unsupported
// or unavailable decisions do not trigger repeated fetches.

import type { EquityResponse } from '../types/equity';
import type { EquityMeta } from '../types/meta';

export type EquityStatus =
  | 'ok'
  | 'skipped'
  | 'disabled'
  | 'unsupported'
  | 'route-missing'
  | 'timeout'
  | 'error';

export interface EquityRecord {
  data: EquityResponse | null;
  status: EquityStatus;
  error?: string;
  /** Optional origin for the villain range (e.g. chart/default/random). */
  origin?: string;
}

const equityCache: Map<string, EquityRecord> = new Map();
const equityInFlight: Map<string, Promise<EquityRecord>> = new Map();

export function getEquity(key: string): EquityRecord | undefined {
  return equityCache.get(key);
}

export function setEquity(key: string, value: EquityRecord): void {
  equityCache.set(key, value);
}

export function getEquityInFlight(key: string): Promise<EquityRecord> | undefined {
  return equityInFlight.get(key);
}

export function setEquityInFlight(key: string, promise: Promise<EquityRecord>): void {
  equityInFlight.set(key, promise);
}

export function deleteEquityInFlight(key: string): void {
  equityInFlight.delete(key);
}

/** Remove all cached equity values.  Useful for testing. */
export function clearEquityCaches(): void {
  equityCache.clear();
  equityInFlight.clear();
}