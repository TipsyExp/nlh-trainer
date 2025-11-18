// frontend/utils/meta.ts
// Client for the /api/meta endpoint with simple session caching.
//
// The guidance overlay fetches a snapshot of backend capabilities via
// GET /api/meta so it can decide whether to attempt equity calls and
// how to label the backend in the UI.  To avoid redundant requests
// this module caches the meta response in memory for a short period of
// time (default 10 minutes).  If the call fails or the response is
// malformed, conservative defaults are returned so that the overlay
// behaves safely (e.g. assumes ranges are not supported).

import { getJson } from './http';
import type { Meta, EquityMeta } from '../types/meta';

interface CachedMeta {
  meta: Meta;
  fetchedAt: number;
}

// Cache lifetime in milliseconds (10 minutes).  After this window the
// client will refetch from the server when getMeta() is called again.
const META_CACHE_TTL_MS = 10 * 60 * 1000;

let cached: CachedMeta | null = null;

/**
 * Return the cached meta snapshot if it is fresh; otherwise fetch
 * /api/meta from the backend and cache the result.  A caller may
 * provide an AbortSignal to cancel the request early.  On error a
 * conservative default is returned (supports_ranges=false, max_players=2,
 * coach.disabled) so that the overlay does not attempt unsupported
 * functionality.
 */
export async function getMeta(opts?: { signal?: AbortSignal }): Promise<Meta> {
  const now = Date.now();
  if (cached && now - cached.fetchedAt < META_CACHE_TTL_MS) {
    // eslint-disable-next-line no-console
    if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
      try {
        console.debug('[equity] meta cached', cached.meta);
      } catch {
        /* noop */
      }
    }
    return cached.meta;
  }
  try {
    const res = await getJson('/api/meta', { signal: opts?.signal });
    if (res.ok && res.status === 200 && res.body) {
      const body = res.body as any;
      // Validate partial shape; fall back gracefully if fields missing.
      const equity: EquityMeta = {
        backend: (body?.equity?.backend as any) || 'unknown',
        supports_ranges: !!body?.equity?.supports_ranges,
        max_players: typeof body?.equity?.max_players === 'number' ? body.equity.max_players : 2,
      };
      const meta: Meta = {
        equity,
        coach: {
          enabled: !!body?.coach?.enabled,
        },
      };
      cached = { meta, fetchedAt: now };
      // eslint-disable-next-line no-console
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        try {
          console.debug('[equity] meta', meta);
        } catch {
          /* noop */
        }
      }
      return meta;
    }
  } catch (e) {
    // swallow fetch errors; will fall through to default
  }
  // Default conservative meta when unavailable or error occurred.
  const defaultMeta: Meta = {
    equity: { backend: 'unknown', supports_ranges: false, max_players: 2 },
    coach: { enabled: false },
  };
  cached = { meta: defaultMeta, fetchedAt: now };
  return defaultMeta;
}
