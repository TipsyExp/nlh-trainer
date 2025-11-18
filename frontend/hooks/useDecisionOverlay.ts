//frontend/hooks/useDecisionOverlay.ts
// Hook to fetch and cache preflop coach advice for the guidance overlay.
//
// This hook coordinates the logic required to obtain preflop advice from
// the backend, dedupe concurrent requests, cache responses by
// (hand_id, idx) and react to changes in the overlay gate or decision
// context.  It exposes a structured coach state along with a
// recommendedAction derived from the returned bucket.  If the overlay
// is disabled, not on the preflop street, or the hand_id/idx are
// missing, the hook returns a null state and does not initiate any
// network requests.

import { useEffect, useState, useMemo } from 'react';
import { getJson } from '../utils/http';
import {
  getCoach,
  setCoach,
  getCoachInFlight,
  setCoachInFlight,
  deleteCoachInFlight,
  type CoachResponse,
} from '../utils/overlayCache';
import { mapCoachToAction } from '../utils/coachMapping';
import type { DecisionContext } from '../types/decision';
import type { CoachAdvice } from '../types/coach';

// Default client timeout for the coach endpoint (in ms).  This can be
// overridden at build time via the NEXT_PUBLIC_COACH_CLIENT_TIMEOUT_MS
// environment variable.  A modest timeout helps keep the UI responsive
// when the backend is slow or unreachable.
const DEFAULT_TIMEOUT_MS = 2000;
const COACH_TIMEOUT_MS = (() => {
  const raw = process.env.NEXT_PUBLIC_COACH_CLIENT_TIMEOUT_MS;
  const n = raw ? parseInt(String(raw), 10) : NaN;
  return !Number.isNaN(n) && n > 0 ? n : DEFAULT_TIMEOUT_MS;
})();

// Convert HTTP status codes into normalised coach statuses.  HTTP 501
// becomes 'disabled', 404 becomes 'not_found', timeouts become
// 'unavailable' and all other non‑200 codes fall back to 'unavailable'.
function statusFromResult(res: { ok: boolean; status: number | 'timeout' }):
  | 'ok'
  | 'disabled'
  | 'not_found'
  | 'unavailable' {
  if (res.status === 'timeout') return 'unavailable';
  if (res.ok) return 'ok';
  if (res.status === 501) return 'disabled';
  if (res.status === 404) return 'not_found';
  return 'unavailable';
}

export interface UseDecisionOverlayResult {
  coach: {
    data: CoachAdvice | null;
    loading: boolean;
    status: 'ok' | 'loading' | 'disabled' | 'not_found' | 'unavailable';
    error?: string;
  };
  recommendedAction: string | null;
}

export function useDecisionOverlay(
  context: DecisionContext | null,
  overlayEnabled: boolean
): UseDecisionOverlayResult {
  // Store the current response record.  A null value indicates that
  // loading has not started yet for the current context.
  const [response, setResponse] = useState<CoachResponse | null>(null);

  useEffect(() => {
    // Determine if we should attempt to fetch advice.  Only fetch when
    // the overlay is enabled, the street is preflop, and both handId
    // and idx are defined.
    const shouldFetch =
      overlayEnabled &&
      context !== null &&
      context.street?.toLowerCase() === 'preflop' &&
      !!context.handId &&
      typeof context.idx === 'number';
    if (!shouldFetch) {
      setResponse(null);
      return;
    }
    const key = `${context.handId}:${context.idx}:preflop`;
    // Return cached value immediately if present.
    const cached = getCoach(key);
    if (cached) {
      // eslint-disable-next-line no-console
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        try {
          console.debug('[coach] cached', key);
        } catch {
          /* noop */
        }
      }
      setResponse(cached);
      return;
    }
    // If a request is already in flight for this key, subscribe to it.
    const existing = getCoachInFlight(key);
    if (existing) {
      existing.then((res) => {
        setResponse(res);
      });
      return;
    }
    // Otherwise initiate a new fetch.  We'll abort the request if the
    // component unmounts or the context changes (to avoid leaking).
    const abortController = new AbortController();
    const prom: Promise<CoachResponse> = (async () => {
      // eslint-disable-next-line no-console
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        try {
          console.debug('[coach] fetch', {
            hand_id: context.handId,
            idx: context.idx,
          });
        } catch {
          /* noop */
        }
      }
      try {
        const res = await getJson(
          `/api/coach/preflop?hand_id=${encodeURIComponent(
            String(context.handId)
          )}&idx=${context.idx}`,
          { timeoutMs: COACH_TIMEOUT_MS, signal: abortController.signal }
        );
        const status = statusFromResult(res);
        if (status === 'ok') {
          // Treat the body as CoachAdvice.  If the shape does not match
          // expectations the overlay will display fallback values.
          const data = res.body as CoachAdvice;
          const resp: CoachResponse = { data, status };
          setCoach(key, resp);
          return resp;
        } else {
          // Negative cache entry; do not retry until context changes.
          const resp: CoachResponse = {
            data: null,
            status,
            error:
              status === 'disabled'
                ? 'Coach disabled'
                : status === 'not_found'
                ? 'Coach route not available'
                : 'Coach unavailable',
          };
          setCoach(key, resp);
          return resp;
        }
      } catch (e: any) {
        // Unexpected errors treat as unavailable.  Do not throw; cache and return.
        const resp: CoachResponse = {
          data: null,
          status: 'unavailable',
          error: e?.message || 'Coach unavailable',
        };
        setCoach(key, resp);
        return resp;
      } finally {
        deleteCoachInFlight(key);
      }
    })();
    setCoachInFlight(key, prom);
    prom.then((res) => {
      setResponse(res);
    });
    return () => {
      abortController.abort();
    };
    // We intentionally include only the fields that change the fetch key
    // or the gating logic.  Other context properties (heroCards, pot)
    // are not relevant to this hook.
  }, [context?.handId, context?.idx, context?.street, overlayEnabled]);

  // Derive the coach state for the caller.  A null response
  // indicates a loading state.  When the overlay is off or not
  // preflop, we surface a disabled state to the UI.
  const coachState = useMemo(() => {
    if (!overlayEnabled) {
      return {
        data: null,
        loading: false,
        status: 'disabled' as const,
        error: undefined,
      };
    }
    const isPreflop = context?.street?.toLowerCase() === 'preflop';
    if (!isPreflop) {
      // Do not fetch on non‑preflop streets; treat as unavailable but
      // without triggering network.
      return {
        data: null,
        loading: false,
        status: 'not_found' as const,
        error: 'Preflop only',
      };
    }
    if (response === null) {
      return {
        data: null,
        loading: true,
        status: 'loading' as const,
        error: undefined,
      };
    }
    // Extend loading when status is unavailable but we still want to show
    // a spinner until the request resolves.
    if (response.status === 'ok') {
      return {
        data: response.data,
        loading: false,
        status: 'ok' as const,
        error: undefined,
      };
    }
    return {
      data: null,
      loading: false,
      status: response.status as any,
      error: response.error,
    };
  }, [response, overlayEnabled, context?.street]);

  // Compute a recommended action key for the UI.  This uses the
  // coachMapping helper to map the bucket into a button key.  When no
  // mapping is possible or the coach status is not ok, returns null.
  const recommendedAction = useMemo(() => {
    if (!context) return null;
    if (coachState.status !== 'ok' || !coachState.data) return null;
    const bucket = coachState.data.bucket;
    const toCall = context.toCall ?? 0;
    // Presets are not part of DecisionContext; the calling component
    // should supply them separately via its own state.  Return the
    // bucket itself for raise sizes; the caller can reconcile with
    // available presets.
    // Map using an empty presets list so that raise sizes are passed
    // through verbatim; fallback logic will be applied in the caller.
    return mapCoachToAction(bucket, toCall, []);
  }, [coachState, context]);

  return { coach: coachState, recommendedAction };
}