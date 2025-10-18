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
    getJSON<{ state: any; actor?: { seat: number; to_call: number; allowed_buckets: string[] } }>(
      "/api/hand/state"
    ),

  postAction: (payload: { seat: number; action: string; amount?: number }) =>
    postJSON<{ ok: boolean; bots_applied: any[]; state: any }>("/api/hand/action", payload),
};
