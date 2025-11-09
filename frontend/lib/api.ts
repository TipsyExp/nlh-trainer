// frontend/lib/api.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

// Gate dev-only /api/hand/auto. Keep default false unless explicitly enabled.
const AUTO_HAND_ENABLED = ["1", "true", "yes", "on"].includes(
  String(process.env.NEXT_PUBLIC_ENABLE_HAND_AUTO || "").toLowerCase()
);

type Json = Record<string, any>;

/** ---- Shared Types (frontend) ---- **/

export type AllowedContext = {
  to_call: number;
  min_raise: number;
  allowed_buckets: string[]; // e.g. ["call","2.2x","2.5x","3.0x","jam"]
};

export type PlayerPublic = {
  seat: number;
  hole_cards: [string, string] | string[]; // human shows real; bots may be ["XX","XX"]
};

export type TableShape = {
  seats: number;
  sb: number;
  bb: number;
  ante: number;
  button: number;
  sb_seat: number;
  bb_seat: number;
};

export type HandState = {
  table: TableShape;
  players: PlayerPublic[];
  street: string; // "preflop" | "flop" | "turn" | "river" | "showdown"
  deck_seed?: string | null;
  last_action?: any;

  // New / important keys:
  pot_total?: number; // stable, cumulative pot
  to_act?: number | null; // current seat index to act (if any)
  allowed?: AllowedContext; // legal context for current actor

  [key: string]: any;
};

export type Actor = {
  seat: number;
  to_call: number;
  allowed_buckets: string[];
  min_raise?: number;
};

export type StateResponse = {
  state: HandState;
  actor?: Actor | null; // legacy fallback; UI should prefer state.to_act + state.allowed
  hand_id?: string;
  idx?: number;
};

export type ActionResponse = {
  ok: boolean;
  bots_applied: Array<{ seat: number; action: string; amount?: number }>;
  state: HandState;
  hand_id?: string;
  idx?: number;
};

export type SessionResponse = {
  ok: boolean;
  detail: string;
  session_id: number;
};

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
async function getCoachAdvice(handId: string, idx: number) {
  const url = `/api/coach/advice?hand_id=${encodeURIComponent(handId)}&idx=${idx}`;
  const r = await fetch(`${API_BASE}${url}`, { method: "GET" });
  const json = await r
    .json()
    .catch(async () => ({ detail: await r.text().catch(() => "") }));
  if (!r.ok) {
    const status = json?.meta?.status || json?.detail || "error";
    throw new Error(
      typeof status === "string" ? `GET ${url} failed: ${r.status} ${status}` : "error"
    );
  }
  return json;
}

// Raw variant that NEVER throws (for debug UI)
async function getCoachAdviceRaw(handId: string, idx: number) {
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
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
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
