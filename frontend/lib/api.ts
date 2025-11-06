// frontend/lib/api.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

type Json = Record<string, any>;

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

// Normal helper that throws on non-200s (used by non-debug paths)
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

// Raw variant that NEVER throws; returns status + parsed body.
// Perfect for debug UI.
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
    url: urlPath, // relative path (nicer in logs)
    body,
  };
}

export const Api = {
  startSession: (payload: {
    seats: number;
    sb: number;
    bb: number;
    ante: number;
    stacks: number[];
    base_seed: string;
    human_seat: number;
  }) => postJSON<{ ok: boolean; detail?: string }>("/api/session", payload),

  startHand: () => postJSON<{ hand_id: string }>("/api/hand/start", {}),

  getState: () =>
    getJSON<{ state: any; actor?: { seat: number; to_call: number; allowed_buckets: string[] }; hand_id?: string; idx?: number }>(
      "/api/hand/state"
    ),

  postAction: (payload: { seat: number; action: string; amount?: number }) =>
    postJSON<{ ok: boolean; bots_applied: any[]; state: any; hand_id?: string; idx?: number }>(
      "/api/hand/action",
      payload
    ),

  // Coach endpoints
  getCoachAdvice,
  getCoachAdviceRaw,
};
