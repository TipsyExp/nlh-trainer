// frontend/pages/table.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { Api, type AllowedContext, type HandState, type Actor } from "../lib/api";
import { CoachPanel } from "../components/CoachPanel";

const COACH_TOGGLE_KEY = "coachEnabled";
const HUMAN_SEAT_KEY = "humanSeat";

// Gate dev-only /api/hand/auto. Default is false unless explicitly enabled.
const AUTO_HAND_ENABLED = ["1", "true", "yes", "on"].includes(
  String(process.env.NEXT_PUBLIC_ENABLE_HAND_AUTO || "").toLowerCase()
);
const DEV_TOOLS = ["1", "true", "yes", "on"].includes(
  String(process.env.NEXT_PUBLIC_DEV_TOOLS || "").toLowerCase()
);

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

export default function TablePage() {
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState<HandState | null>(null);
  const [actor, setActor] = useState<Actor | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [coachEnabled, setCoachEnabled] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const raw = localStorage.getItem(COACH_TOGGLE_KEY);
    return raw === "1";
  });
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(COACH_TOGGLE_KEY, coachEnabled ? "1" : "0");
    }
  }, [coachEnabled]);

  const [handId, setHandId] = useState<string | null>(null);

  const humanSeat =
    typeof window !== "undefined" ? parseInt(localStorage.getItem(HUMAN_SEAT_KEY) || "0", 10) : 0;

  const bb = useMemo(() => state?.table?.bb ?? 100, [state]);

  const pot = useMemo(
    () => (state?.pot_total ?? (state as any)?.pot_after ?? (state as any)?.pot ?? 0),
    [state]
  );

  // Prefer state.allowed/to_act if present; fallback to legacy actor
  const allowedCtx: AllowedContext | null = useMemo(() => {
    if (!state) return null;
    if (state.allowed && typeof state.allowed.to_call === "number") return state.allowed;
    if (actor) {
      return {
        to_call: actor.to_call,
        min_raise: actor.min_raise ?? Math.max(100, bb),
        allowed_buckets: actor.allowed_buckets || [],
      };
    }
    return null;
  }, [state, actor, bb]);

  const toActSeat = state?.to_act ?? actor?.seat ?? null;
  const canAct = toActSeat === humanSeat;
  const waitingOnBots =
    !!state && state.street !== "showdown" && !canAct && toActSeat !== null && toActSeat !== undefined;

  const refresh = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const r = await Api.getState();
      setState(r.state);
      setActor(r.actor ?? null);
      const sid = (r as any)?.hand_id ?? r?.state?.hand_id ?? r?.state?.handId ?? null;
      if (sid) setHandId(String(sid));
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onStartHand = async () => {
    setErr(null);
    setLoading(true);
    try {
      const res = await Api.startHand();
      if (res?.hand_id) setHandId(String(res.hand_id));
      await refresh();
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  async function pollUntilSettled(humanSeat: number) {
    // Poll GET /api/hand/state until it's our turn or the hand is over.
    // In dev we *also* try /api/hand/auto to actively advance bots each cycle.
    let safety = 64;
    while (safety-- > 0) {
      const snap = await Api.getState();
      setState(snap.state);
      setActor(snap.actor ?? null);

      const sid = (snap as any)?.hand_id ?? snap?.state?.hand_id ?? snap?.state?.handId ?? null;
      if (sid) setHandId(String(sid));

      const nextSeat = snap?.state?.to_act ?? snap?.actor?.seat ?? null;
      const finished = snap?.state?.street === "showdown";
      const heroTurn = nextSeat === humanSeat;

      if (finished || heroTurn) break;

      if (AUTO_HAND_ENABLED) {
        try {
          const auto = await Api.autoPlay();
          if (!auto?.ok) {
            // Continue polling without auto
          }
        } catch {
          // Swallow and continue polling without auto
        }
      }

      await sleep(100);
    }
  }

  async function postAction(action: string, amount?: number) {
    if (!allowedCtx) return;
    setErr(null);
    setLoading(true);
    try {
      const res = await Api.postAction({ seat: humanSeat, action, amount });
      setState(res.state);
      await pollUntilSettled(humanSeat);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // Preflop open helpers
  function amountForOpenLabel(label: string): number | undefined {
    const m = label.match(/^(\d+(?:\.\d+)?)x$/);
    if (!m) return undefined;
    const mult = parseFloat(m[1]);
    return Math.round(mult * bb);
  }
  function jamAmount(): number {
    return 1_000_000_000;
  }

  // Decision idx (best-effort)
  const decisionIdx =
    typeof (state as any)?.decision_idx === "number"
      ? (state as any).decision_idx
      : canAct
      ? 0
      : null;

  const coachShouldShow =
    coachEnabled && canAct && state && state.street !== "preflop" && decisionIdx !== null;

  // Dev util: copy raw state
  const copyState = async () => {
    if (!state) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(state, null, 2));
    } catch {
      // noop
    }
  };

  // 🚩 Choose the correct action verb for sized actions
  const actionVerb = allowedCtx?.to_call === 0 ? "bet" : "raise";

  return (
    <main className="min-h-screen p-6 bg-gray-50">
      <div className="max-w-5xl mx-auto grid gap-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">NLH Trainer — Table</h1>
          <div className="flex items-center gap-3">
            {waitingOnBots && (
              <span className="text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-800">
                Bots thinking…
              </span>
            )}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={coachEnabled}
                onChange={(e) => setCoachEnabled(e.target.checked)}
              />
              <span>Coach</span>
            </label>
            <button
              onClick={onStartHand}
              className="rounded-xl bg-black text-white px-4 py-2 disabled:opacity-50"
              disabled={loading}
            >
              {loading ? "Working…" : "Start Hand"}
            </button>
            <button
              onClick={refresh}
              className="rounded-xl border px-4 py-2 disabled:opacity-50"
              disabled={loading}
            >
              Refresh
            </button>
            {DEV_TOOLS && (
              <button
                onClick={copyState}
                className="rounded-xl border px-3 py-2 text-xs disabled:opacity-50"
                disabled={!state}
                title="Copy /api/hand/state JSON"
              >
                Copy state
              </button>
            )}
          </div>
        </header>

        {err && <div className="rounded-xl bg-red-50 text-red-700 p-3">{err}</div>}

        {/* Snapshot */}
        {state && (
          <div className="grid md:grid-cols-3 gap-4">
            <div className="rounded-2xl bg-white shadow p-4 space-y-2">
              <h2 className="font-semibold">Table</h2>
              <div className="text-sm text-gray-700">
                <div>Seats: {state.table.seats}</div>
                <div>Blinds: {state.table.sb}/{state.table.bb}</div>
                <div>Button: {state.table.button}</div>
                <div>SB Seat: {state.table.sb_seat}</div>
                <div>BB Seat: {state.table.bb_seat}</div>
                <div>Street: {state.street}</div>
                <div>Pot: {pot}</div>
                <div className="text-gray-500 text-xs">Seed: {state.deck_seed}</div>
                {handId && <div className="text-gray-500 text-xs">Hand: {handId}</div>}
                {typeof decisionIdx === "number" && (
                  <div className="text-gray-500 text-xs">Decision: {decisionIdx}</div>
                )}
              </div>
            </div>

            <div className="rounded-2xl bg-white shadow p-4 space-y-2 md:col-span-2">
              <h2 className="font-semibold">Players</h2>
              <div className="grid sm:grid-cols-2 gap-3">
                {state.players.map((p: any) => (
                  <div
                    key={p.seat}
                    className={`rounded-xl border p-3 ${
                      p.seat === humanSeat ? "border-black" : "border-gray-200"
                    }`}
                  >
                    <div className="text-sm font-medium">
                      Seat {p.seat} {p.seat === humanSeat && "(You)"}
                    </div>
                    <div className="text-sm text-gray-700">
                      Hand: {p.hole_cards[0]} {p.hole_cards[1]}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Action Panel */}
        {canAct && allowedCtx && state && (
          <div className="rounded-2xl bg-white shadow p-4 space-y-4">
            <h2 className="font-semibold">Your Action</h2>
            <div className="text-sm text-gray-700">
              <div>To call: {allowedCtx.to_call}</div>
              <div className="text-xs text-gray-500">
                Allowed: {allowedCtx.allowed_buckets.join(", ")}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {/* If to_call == 0, "check" is legal */}
              {allowedCtx.to_call === 0 && (
                <button
                  onClick={() => postAction("check")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Check
                </button>
              )}

              {/* If to_call > 0, "call" is legal */}
              {allowedCtx.to_call > 0 && allowedCtx.allowed_buckets.includes("call") && (
                <button
                  onClick={() => postAction("call")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Call {allowedCtx.to_call}
                </button>
              )}

              {/* Quick open sizes (engine snaps; verb chosen by to_call === 0 ? bet : raise) */}
              {allowedCtx.allowed_buckets
                .filter((b) => /^\d+(\.\d+)?x$/.test(b))
                .map((label) => {
                  const amt = amountForOpenLabel(label);
                  return (
                    <button
                      key={label}
                      onClick={() => postAction(actionVerb, amt)}
                      className="rounded-xl bg-black text-white px-3 py-2 disabled:opacity-50"
                      disabled={loading}
                      title={`Total ${amt}`}
                    >
                      Raise {label}
                    </button>
                  );
                })}

              {/* Jam (same verb rule) */}
              {allowedCtx.allowed_buckets.includes("jam") && (
                <button
                  onClick={() => postAction(actionVerb, jamAmount())}
                  className="rounded-xl bg-red-600 text-white px-3 py-2 disabled:opacity-50"
                  disabled={loading}
                >
                  Jam
                </button>
              )}
            </div>

            {/* Custom sized action (verb chosen by to_call === 0 ? bet : raise) */}
            <CustomRaise
              disabled={loading}
              onSubmit={(amt) => postAction(actionVerb, amt)}
            />
          </div>
        )}

        {/* Coach Panel (postflop, human turn only) */}
        {coachShouldShow && <CoachPanel enabled={true} handId={handId} idx={decisionIdx} />}

        {/* Last action panel */}
        {state?.last_action && (
          <div className="rounded-2xl bg-white shadow p-4 space-y-1">
            <h2 className="font-semibold">Last Action</h2>
            <pre className="text-xs bg-gray-50 rounded-xl p-3 overflow-auto">
              {JSON.stringify(state.last_action, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </main>
  );
}

function CustomRaise({
  disabled,
  onSubmit,
}: {
  disabled?: boolean;
  onSubmit: (amount: number) => void;
}) {
  const [val, setVal] = useState<string>("");

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const n = parseInt(val, 10);
        if (!Number.isNaN(n) && n > 0) onSubmit(n);
      }}
    >
      <input
        type="number"
        min={1}
        placeholder="Custom total"
        className="rounded-lg border p-2"
        value={val}
        onChange={(e) => setVal(e.target.value)}
      />
      <button
        type="submit"
        className="rounded-xl border px-3 py-2 disabled:opacity-50"
        disabled={disabled}
      >
        Raise (custom)
      </button>
    </form>
  );
}
