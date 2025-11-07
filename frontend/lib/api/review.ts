// frontend/lib/api/review.ts
import type {
  GetReviewHandsResponse,
  GetReviewHandResponse,
} from '../types/review';

const API_BASE =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_BASE) || '';

/**
 * Build an absolute or relative API URL.
 * If NEXT_PUBLIC_API_BASE is set (e.g., http://127.0.0.1:8000), we prefix with it.
 * Otherwise we hit the Next.js proxy (same origin) at /api/...
 */
function apiUrl(path: string): string {
  if (!API_BASE) return path;
  // Ensure no duplicate slashes
  return `${API_BASE.replace(/\/+$/, '')}${path}`;
}

async function getJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(
      `GET ${url} failed: ${res.status} ${res.statusText}${text ? ` — ${text}` : ''}`
    );
  }
  return (await res.json()) as T;
}

/**
 * Fetch list of recent hands for review.
 * @param limit number of rows to return (default 100)
 * @param signal optional AbortSignal
 */
export async function getReviewHands(
  limit: number = 100,
  signal?: AbortSignal
): Promise<GetReviewHandsResponse> {
  const url = apiUrl(`/api/review/hands?limit=${encodeURIComponent(limit)}`);
  return getJSON<GetReviewHandsResponse>(url, signal);
}

/**
 * Fetch detailed review payload for a single hand.
 * @param handId hand identifier
 * @param signal optional AbortSignal
 */
export async function getReviewHand(
  handId: string,
  signal?: AbortSignal
): Promise<GetReviewHandResponse> {
  const url = apiUrl(`/api/review/hand/${encodeURIComponent(handId)}`);
  return getJSON<GetReviewHandResponse>(url, signal);
}
