// Lightweight HTTP helper with timeout and abort support.
//
// This module wraps the native fetch API to provide a unified way to
// perform JSON GET/POST requests with an optional timeout and the
// ability to abort via a caller-provided signal. The helper returns a
// tuple with metadata about the response rather than throwing on HTTP
// errors, allowing callers to categorise error states (e.g. 501 vs 404
// vs timeout) without catching exceptions.
//
// Typical callers include:
//   - GET /api/meta                      (capabilities)
//   - GET /api/coach/advice?hand_id=... (unified coach advice)
//   - POST /api/equity                  (equity calculations)

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? '').replace(/\/$/, '') || '';

export interface JsonResponse {
  ok: boolean;
  /** HTTP status code (e.g. 200, 404) or the string 'timeout' when aborted */
  status: number | 'timeout';
  /** Parsed JSON body, plain text or null when unavailable */
  body: any;
}

/**
 * Perform a JSON POST request against the backend API with optional
 * timeout and abort signalling. The returned object always contains
 * `ok`, `status` and `body` fields regardless of HTTP success. When the
 * request is aborted due to timeout or an external abort signal the
 * status is set to `'timeout'`.
 *
 * @param path Relative path beginning with '/' (e.g. '/api/equity').
 * @param body JSON-serialisable payload to send in the request body.
 * @param opts Optional timeout in milliseconds and AbortSignal from caller.
 */
export async function postJson(
  path: string,
  body: any,
  opts?: { timeoutMs?: number; signal?: AbortSignal }
): Promise<JsonResponse> {
  const timeoutMs = opts?.timeoutMs;
  const externalSignal = opts?.signal;
  const timeoutController = new AbortController();
  const timeoutId =
    typeof timeoutMs === 'number'
      ? setTimeout(() => {
          timeoutController.abort();
        }, timeoutMs)
      : undefined;
  // Combine external signal and timeout signal
  let combinedSignal: AbortSignal;
  if (externalSignal) {
    const combinedController = new AbortController();
    function propagateAbort() {
      combinedController.abort();
    }
    if (externalSignal.aborted) {
      combinedController.abort();
    } else {
      externalSignal.addEventListener('abort', propagateAbort);
    }
    timeoutController.signal.addEventListener('abort', propagateAbort);
    combinedSignal = combinedController.signal;
  } else {
    combinedSignal = timeoutController.signal;
  }
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: combinedSignal,
    });
    let resBody: any = null;
    try {
      resBody = await res.json();
    } catch {
      try {
        resBody = await res.text();
      } catch {
        resBody = null;
      }
    }
    return { ok: res.ok, status: res.status, body: resBody };
  } catch (err: any) {
    if (err && typeof err === 'object' && err.name === 'AbortError') {
      return { ok: false, status: 'timeout', body: null };
    }
    throw err;
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

/**
 * Perform a JSON GET request against the backend API with optional
 * timeout and abort signalling. The returned object always contains
 * `ok`, `status` and `body` fields regardless of HTTP success. When
 * the request is aborted due to timeout or an external abort signal
 * the status is set to `'timeout'`.
 *
 * @param path Relative path beginning with '/' (e.g. '/api/meta' or '/api/coach/advice?hand_id=H1&idx=0').
 * @param opts Optional timeout in milliseconds and AbortSignal from caller.
 */
export async function getJson(
  path: string,
  opts?: { timeoutMs?: number; signal?: AbortSignal }
): Promise<JsonResponse> {
  const timeoutMs = opts?.timeoutMs;
  const externalSignal = opts?.signal;
  // Controller used to enforce timeout; will be aborted via timer below.
  const timeoutController = new AbortController();
  const timeoutId =
    typeof timeoutMs === 'number'
      ? setTimeout(() => {
          timeoutController.abort();
        }, timeoutMs)
      : undefined;
  // If the caller provided a signal, combine it with our timeout signal.
  let combinedSignal: AbortSignal;
  if (externalSignal) {
    // Create a controller that follows whichever signal fires first.
    const combinedController = new AbortController();
    function propagateAbort() {
      combinedController.abort();
    }
    if (externalSignal.aborted) {
      // Propagate synchronously if already aborted.
      combinedController.abort();
    } else {
      externalSignal.addEventListener('abort', propagateAbort);
    }
    timeoutController.signal.addEventListener('abort', propagateAbort);
    combinedSignal = combinedController.signal;
  } else {
    combinedSignal = timeoutController.signal;
  }
  try {
    const res = await fetch(`${API_BASE}${path}`, { method: 'GET', signal: combinedSignal });
    let body: any = null;
    try {
      body = await res.json();
    } catch {
      try {
        body = await res.text();
      } catch {
        body = null;
      }
    }
    return { ok: res.ok, status: res.status, body };
  } catch (err: any) {
    // Distinguish timeout from other network errors by checking AbortError.
    if (err && typeof err === 'object' && err.name === 'AbortError') {
      return { ok: false, status: 'timeout', body: null };
    }
    throw err;
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}
