// frontend/lib/api.ts
// Updated API client for the NLH Trainer frontend.
//
// This file wraps the backend REST API and re-exports shared types. It
// imports type definitions from `./types/hand` and `../types/advice` to
// ensure that the shape of `HandState`, `AllowedContext`, and advice types
// remain consistent across the codebase.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

// Gate dev-only /api/hand/auto. Keep default false unless explicitly enabled.
const AUTO_HAND_ENABLED = ["1", "true", "yes", "on"].includes(
  String(process.env.NEXT_PUBLIC_ENABLE_HAND_AUTO || "").toLowerCase(),
);

type Json = Record<string, any>;

/** ---- Shared Types (re-exported from ./types/hand) ---- **/

import type {
  HandState,
  AllowedContext,
  PlayerPublic,
  TableShape,
  Actor,
  StateResponse,
  ActionResponse,
  SessionResponse,
} from "./types/hand";

import type { AdvicePayloadV1 } from "../types/advice";

/** ---- Low-level HTTP helpers ---- **/

async function postJSON<T = any>(path: string, body: Json): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.detail || JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(`POST ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

async function getJSON<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.detail || JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(`GET ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

/** ---- Coach helpers ---- **/

// Throws on non-200 (for main UI)
async function getCoachAdvice(handId: string, idx: number): Promise<AdvicePayloadV1> {
  const url = `/api/coach/advice?hand_id=${encodeURIComponent(handId)}&idx=${idx}`;
  const r = await fetch(`${API_BASE}${url}`, { method: "GET" });

  let json: any;
  try {
    json = await r.json();
  } catch {
    const text = await r.text().catch(() => "");
    throw new Error(`GET ${url} failed: ${r.status} ${text || "error"}`);
  }

  if (!r.ok) {
    const msg =
      (typeof json?.detail === "string" && json.detail) ||
      (typeof json?.error === "string" && json.error) ||
      "";
    throw new Error(`GET ${url} failed: ${r.status} ${msg || "error"}`);
  }

  return json as AdvicePayloadV1;
}

// Raw variant that NEVER throws (for debug UI)
async function getCoachAdviceRaw(handId: string, idx: number): Promise<{
  ok: boolean;
  status: number;
  disabled: boolean;
  url: string;
  body: any;
}> {
  const urlPath = `/api/coach/advice?hand_id=${encodeURIComponent(handId)}&idx=${idx}`;
  const url = `${API_BASE}${urlPath}`;
  const res = await fetch(url, { method: "GET" });

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

  return {
    ok: res.ok,
    status: res.status,
    disabled: res.status === 501,
    url: urlPath, // relative (nicer in logs)
    body,
  };
}

/** ---- Public API ---- **/

export const Api = {
  startSession: (payload: {
    seats: number;
    sb: number;
    bb: number;
    ante?: number;
    stacks: number[];
    base_seed?: string | null;
    human_seat: number;
    bot_mode?: "none" | "heuristic" | "rlcard" | null;
    bot_time_budget_ms?: number | null;
    rlcard_model_path?: string | null;
  }) => postJSON<SessionResponse>("/api/session", payload),

  startHand: () => postJSON<{ hand_id: string }>("/api/hand/start", {}),

  getState: () => getJSON<StateResponse>("/api/hand/state"),

  postAction: (payload: { seat: number; action: string; amount?: number }) =>
    postJSON<ActionResponse>("/api/hand/action", payload),

  /**
   * DEV helper: POST /api/hand/auto to advance bots once.
   * - Gated by NEXT_PUBLIC_ENABLE_HAND_AUTO.
   * - Maps 501 ("disabled") to a soft result { ok:false, disabled:true }.
   * - Never throws; returns { ok:false } on non-200s.
   */
  autoPlay: async (): Promise<
    | ({ ok: false; disabled: true } & { error?: string })
    | ({
        ok: true;
        disabled: false;
        state: HandState;
        bots_applied?: Array<{ seat: number; action: string; amount?: number }>;
        hand_id?: string;
        idx?: number;
      } & { error?: string })
    | ({ ok: false; disabled: false } & { error?: string })
  > => {
    if (!AUTO_HAND_ENABLED) {
      return { ok: false, disabled: true };
    }
    const url = `${API_BASE}/api/hand/auto`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (res.status === 501) {
        // Backend gate off — treat as disabled, not an error.
        return { ok: false, disabled: true };
      }
      let payload: any = null;
      try {
        payload = await res.json();
      } catch {
        payload = null;
      }
      if (!res.ok) {
        const detail =
          (payload && (payload.detail || payload.error)) ||
          (await res.text().catch(() => "")) ||
          `status ${res.status}`;
        return { ok: false, disabled: false, error: String(detail) };
      }
      return { ok: true, disabled: false, ...payload };
    } catch (e: any) {
      return { ok: false, disabled: false, error: e?.message || String(e) };
    }
  },

  // Coach endpoints
  getCoachAdvice,
  getCoachAdviceRaw,
};

// Re-export shared types for convenience. This allows other modules to import
// HandState and related types from `../lib/api` as they did previously while
// still sourcing the definitions from `./types/hand`.
export type {
  HandState,
  AllowedContext,
  PlayerPublic,
  TableShape,
  Actor,
  StateResponse,
  ActionResponse,
  SessionResponse,
} from "./types/hand";

// Re-export advice types so callers can do `import { Advice } from "../lib/api"`.
export type { Advice, AdvicePayloadV1 } from "../types/advice";
