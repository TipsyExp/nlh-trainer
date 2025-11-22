// frontend/hooks/useDecisionOverlay.ts
// Hook to fetch and cache coach advice and equity for the guidance overlay.
//
// Current behaviour (M2 / early M3):
// - Uses GET /api/coach/preflop for preflop-only coach advice.
// - Uses POST /api/equity for equity (preflop + postflop), gated by /api/meta.
// - Caches results per (hand_id, idx, street, input signature) and exposes
//   separate coach and equity slices to the overlay.
//
// Planned behaviour (M3+):
// - Migrate to a single, cross-street AdviceV1 payload from
//   GET /api/coach/advice, as defined in docs/COACH-ADVICE-PAYLOAD.md.
// - The hook will then fetch a unified advice object (including equity view)
//   instead of orchestrating separate coach + equity calls. This file’s
//   public return shape is expected to evolve to wrap that AdviceV1 payload.
//
// Until that migration, this hook continues to implement the legacy
// “two-endpoint” flow described above.

import { useEffect, useState, useMemo } from 'react';
import { getJson, postJson } from '../utils/http';
import {
  getCoach,
  setCoach,
  getCoachInFlight,
  setCoachInFlight,
  deleteCoachInFlight,
  type CoachResponse,
  getEquity,
  setEquity,
  getEquityInFlight,
  setEquityInFlight,
  deleteEquityInFlight,
  type EquityRecord,
  type EquityStatus,
} from '../utils/overlayCache';
import { mapCoachToAction } from '../utils/coachMapping';
import { buildPreflopEquityBody, buildPostflopEquityBody } from '../utils/equityParams';
import { useMeta } from './useMeta';
import type { DecisionContext } from '../types/decision';
import type { CoachAdvice } from '../types/coach';
import type { EquityResponse } from '../types/equity';
import type { Meta } from '../types/meta';
import { setOverlayTrace } from '../store/overlayDebugStore';

// Default client timeout for the coach endpoint (in ms). This can be
// overridden at build time via the NEXT_PUBLIC_COACH_CLIENT_TIMEOUT_MS
// environment variable. A modest timeout helps keep the UI responsive
// when the backend is slow or unreachable.
const DEFAULT_TIMEOUT_MS = 2000;
const COACH_TIMEOUT_MS = (() => {
  const raw = process.env.NEXT_PUBLIC_COACH_CLIENT_TIMEOUT_MS;
  const n = raw ? parseInt(String(raw), 10) : NaN;
  return !Number.isNaN(n) && n > 0 ? n : DEFAULT_TIMEOUT_MS;
})();

// Default client timeout for the equity endpoint (in ms). Can be
// overridden via NEXT_PUBLIC_EQUITY_CLIENT_TIMEOUT_MS. A short
// timeout prevents long running Monte Carlo calculations from
// blocking the UI when the backend is slow.
const DEFAULT_EQUITY_TIMEOUT_MS = 2000;
const EQUITY_TIMEOUT_MS = (() => {
  const raw = process.env.NEXT_PUBLIC_EQUITY_CLIENT_TIMEOUT_MS;
  const n = raw ? parseInt(String(raw), 10) : NaN;
  return !Number.isNaN(n) && n > 0 ? n : DEFAULT_EQUITY_TIMEOUT_MS;
})();

// Convert HTTP status codes into normalised coach statuses. HTTP 501
// becomes 'disabled', 404 becomes 'not_found', timeouts become
// 'unavailable' and all other non-200 codes fall back to 'unavailable'.
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
  /** Convenience mapping of coach.bucket -> action key for the UI. */
  recommendedAction: string | null;
  equity: {
    data: EquityResponse | null;
    loading: boolean;
    status: EquityStatus;
    error?: string;
    /** Origin of villain range for preflop (e.g. chart/default/random). */
    origin?: string;
  };
  meta: {
    meta: Meta | null;
    loading: boolean;
    error?: string;
  };
}

export function useDecisionOverlay(
  context: DecisionContext | null,
  overlayEnabled: boolean
): UseDecisionOverlayResult {
  // Fetch meta capabilities once per session.
  const metaState = useMeta();

  // Store the current coach response record. A null value indicates
  // that loading has not started yet for the current context.
  const [coachResponse, setCoachResponse] = useState<CoachResponse | null>(null);
  // Store the current equity response record.
  const [equityResponse, setEquityResponse] = useState<EquityRecord | null>(null);

  // ------------------- Coach fetching -------------------
  useEffect(() => {
    const shouldFetch =
      overlayEnabled &&
      context !== null &&
      context.street?.toLowerCase() === 'preflop' &&
      !!context.handId &&
      typeof context.idx === 'number';

    // Always update overlay trace for current decision; reset calledCoach.
    setOverlayTrace({
      handId: context?.handId ?? null,
      idx: typeof context?.idx === 'number' ? (context?.idx as number) : null,
      street: context?.street ?? null,
      calledCoach: false,
    });

    if (!shouldFetch) {
      setCoachResponse(null);
      return;
    }

    const key = `${context.handId}:${context.idx}:preflop`;

    const cached = getCoach(key);
    if (cached) {
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        // eslint-disable-next-line no-console
        console.debug('[coach] cached', key);
      }
      setCoachResponse(cached);
      return;
    }

    const existing = getCoachInFlight(key);
    if (existing) {
      existing.then((res) => {
        setCoachResponse(res);
      });
      return;
    }

    const abortController = new AbortController();
    const prom: Promise<CoachResponse> = (async () => {
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        // eslint-disable-next-line no-console
        console.debug('[coach] fetch', {
          hand_id: context.handId,
          idx: context.idx,
        });
      }
      // Mark that we made a coach call for this decision.
      setOverlayTrace({ calledCoach: true });
      try {
        const res = await getJson(
          `/api/coach/preflop?hand_id=${encodeURIComponent(
            String(context.handId)
          )}&idx=${context.idx}`,
          { timeoutMs: COACH_TIMEOUT_MS, signal: abortController.signal }
        );
        const status = statusFromResult(res);
        if (status === 'ok') {
          const data = res.body as CoachAdvice;
          const resp: CoachResponse = { data, status };
          setCoach(key, resp);
          return resp;
        } else {
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
      setCoachResponse(res);
    });

    return () => {
      abortController.abort();
    };
  }, [context?.handId, context?.idx, context?.street, overlayEnabled]);

  // ------------------- Equity fetching -------------------
  useEffect(() => {
    // Update trace & reset calledEquity.
    setOverlayTrace({
      handId: context?.handId ?? null,
      idx: typeof context?.idx === 'number' ? (context?.idx as number) : null,
      street: context?.street ?? null,
      calledEquity: false,
    });

    if (!overlayEnabled || !context || !context.handId || typeof context.idx !== 'number') {
      setEquityResponse(null);
      return;
    }

    if (metaState.loading || !metaState.meta) {
      return;
    }

    const street = context.street?.toLowerCase() || '';
    const meta = metaState.meta;
    let build:
      | ReturnType<typeof buildPreflopEquityBody>
      | ReturnType<typeof buildPostflopEquityBody>;

    if (street === 'preflop') {
      if (!meta.equity.supports_ranges) {
        const rec: EquityRecord = {
          data: null,
          status: 'unsupported',
          error: 'Ranges unsupported',
        };
        setEquityResponse(rec);
        return;
      }
      build = buildPreflopEquityBody(context, {
        iters: undefined,
        exact: false,
      });
    } else if (street === 'flop' || street === 'turn' || street === 'river') {
      build = buildPostflopEquityBody(context, {
        iters: undefined,
        exact: false,
        maxPlayers: meta.equity.max_players,
      });
    } else {
      const rec: EquityRecord = {
        data: null,
        status: 'skipped',
      };
      setEquityResponse(rec);
      return;
    }

    if (build.reasonIfSkipped) {
      const rec: EquityRecord = {
        data: null,
        status: 'skipped',
        error: build.reasonIfSkipped,
        origin: build.origin,
      };
      setEquityResponse(rec);
      return;
    }

    const key = `equity:${context.handId}:${context.idx}:${street}:${build.signature}`;

    const cachedEq = getEquity(key);
    if (cachedEq) {
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        // eslint-disable-next-line no-console
        console.debug('[equity] cached', key);
      }
      setEquityResponse(cachedEq);
      return;
    }

    const inflight = getEquityInFlight(key);
    if (inflight) {
      inflight.then((res) => {
        setEquityResponse(res);
      });
      return;
    }

    const abortController = new AbortController();
    const prom: Promise<EquityRecord> = (async () => {
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        // eslint-disable-next-line no-console
        console.debug('[equity] fetch', {
          key,
          body: build.body,
          qs: { hand_id: context.handId, idx: context.idx },
        });
      }
      setOverlayTrace({ calledEquity: true });
      try {
        const res = await postJson(
          `/api/equity?hand_id=${encodeURIComponent(String(context.handId))}&idx=${
            context.idx
          }`,
          build.body,
          { timeoutMs: EQUITY_TIMEOUT_MS, signal: abortController.signal }
        );
        let status: EquityStatus;
        if (res.status === 'timeout') {
          status = 'timeout';
        } else if (res.ok) {
          status = 'ok';
        } else if (res.status === 501) {
          status = 'disabled';
        } else if (res.status === 404) {
          status = 'route-missing';
        } else if (res.status === 400) {
          status = 'unsupported';
        } else {
          status = 'error';
        }
        if (status === 'ok') {
          const data = res.body as EquityResponse;
          const rec: EquityRecord = { data, status, origin: build.origin };
          setEquity(key, rec);
          return rec;
        } else {
          const rec: EquityRecord = {
            data: null,
            status,
            error:
              status === 'disabled'
                ? 'Equity disabled'
                : status === 'route-missing'
                ? 'Equity route not available'
                : status === 'unsupported'
                ? 'Equity unsupported'
                : status === 'timeout'
                ? 'Equity timed out'
                : 'Equity unavailable',
            origin: build.origin,
          };
          setEquity(key, rec);
          return rec;
        }
      } catch (e: any) {
        const rec: EquityRecord = {
          data: null,
          status: 'error',
          error: e?.message || 'Equity unavailable',
          origin: build.origin,
        };
        setEquity(key, rec);
        return rec;
      } finally {
        deleteEquityInFlight(key);
      }
    })();

    setEquityInFlight(key, prom);
    prom.then((res) => {
      setEquityResponse(res);
    });

    return () => {
      abortController.abort();
    };
  }, [
    context?.handId,
    context?.idx,
    context?.street,
    overlayEnabled,
    metaState.meta,
    metaState.loading,
  ]);

  // ------------------- Derived coach state -------------------
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
      return {
        data: null,
        loading: false,
        status: 'not_found' as const,
        error: 'Preflop only',
      };
    }
    if (coachResponse === null) {
      return {
        data: null,
        loading: true,
        status: 'loading' as const,
        error: undefined,
      };
    }
    if (coachResponse.status === 'ok') {
      return {
        data: coachResponse.data,
        loading: false,
        status: 'ok' as const,
        error: undefined,
      };
    }
    return {
      data: null,
      loading: false,
      status: coachResponse.status as any,
      error: coachResponse.error,
    };
  }, [coachResponse, overlayEnabled, context?.street]);

  // Recommended action key derived from coach bucket.
  const recommendedAction = useMemo(() => {
    if (!context) return null;
    if (coachState.status !== 'ok' || !coachState.data) return null;
    const bucket = coachState.data.bucket;
    const toCall = context.toCall ?? 0;
    // We don't know presets here; let caller reconcile if needed.
    return mapCoachToAction(bucket, toCall, []);
  }, [coachState, context]);

  // ------------------- Derived equity state -------------------
  const equityState = useMemo(() => {
    if (!overlayEnabled) {
      return {
        data: null,
        loading: false,
        status: 'skipped' as EquityStatus,
        error: undefined,
        origin: undefined,
      };
    }
    if (metaState.loading) {
      return {
        data: null,
        loading: true,
        status: 'skipped' as EquityStatus,
        error: undefined,
        origin: undefined,
      };
    }
    if (equityResponse === null) {
      return {
        data: null,
        loading: true,
        status: 'skipped' as EquityStatus,
        error: undefined,
        origin: undefined,
      };
    }
    if (equityResponse.status === 'ok') {
      return {
        data: equityResponse.data,
        loading: false,
        status: 'ok' as EquityStatus,
        error: undefined,
        origin: equityResponse.origin,
      };
    }
    return {
      data: null,
      loading: false,
      status: equityResponse.status,
      error: equityResponse.error,
      origin: equityResponse.origin,
    };
  }, [overlayEnabled, metaState.loading, equityResponse]);

  return {
    coach: coachState,
    recommendedAction,
    equity: equityState,
    meta: { meta: metaState.meta, loading: metaState.loading, error: metaState.error },
  };
}
