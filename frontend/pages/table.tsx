// frontend/pages/table.tsx

import { useCallback, useEffect, useMemo, useState } from "react";
import { Api } from "../lib/api";
import type {
  AllowedContext,
  HandState,
  Actor,
  AllowedAction,
} from "../lib/types/hand";
import { CoachPanel } from "../components/CoachPanel";
import { WaitingOverlay } from "../components/WaitingOverlay";
import { BoardRow as CommunityBoardRow } from "../components/common/Cards";

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
  const [botsAdvancing, setBotsAdvancing] = useState(false);

  const COACH_TOGGLE_KEY = "coachEnabled";
  const HUMAN_SEAT_KEY = "humanSeat";

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
    typeof window !== "undefined"
      ? parseInt(localStorage.getItem(HUMAN_SEAT_KEY) || "0", 10)
      : 0;

  const bb = useMemo(() => state?.table?.bb ?? 100, [state]);

  const pot = useMemo(
    () => state?.pot_total ?? (state as any)?.pot_after ?? (state as any)?.pot ?? 0,
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

  const refresh = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const r = await Api.getState();
      setState(r.state);
      setActor(r.actor ?? null);
      const sid =
        (r as any)?.hand_id ??
        r?.state?.hand_id ??
        (r as any)?.state?.handId ??
        null;
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
    // Switch to a time-based cap to handle slower solves gracefully.
    const start = Date.now();
    const maxWaitMs = 30_000; // 30s cap
    let bannerSet = false;

    try {
      while (Date.now() - start < maxWaitMs) {
        const snap = await Api.getState();
        setState(snap.state);
        setActor(snap.actor ?? null);

        const sid =
          (snap as any)?.hand_id ??
          snap?.state?.hand_id ??
          (snap as any)?.state?.handId ??
          null;
        if (sid) setHandId(String(sid));

        const nextSeat = snap?.state?.to_act ?? snap?.actor?.seat ?? null;
        const finished = snap?.state?.street === "showdown";
        const heroTurn = nextSeat === humanSeat;

        if (!finished && !heroTurn && !bannerSet) {
          setBotsAdvancing(true);
          bannerSet = true;
        }
        if (finished || heroTurn) break;

        if (AUTO_HAND_ENABLED) {
          try {
            const auto = await Api.autoPlay();
            if (!auto?.ok) {
              // Continue polling without auto
            }
          } catch {
            // Continue polling without auto
          }
        }

        await sleep(150);
      }
    } finally {
      setBotsAdvancing(false);
    }
  }

  async function postAction(action: string, amount?: number) {
    if (!allowedCtx) return;
    setErr(null);
    setLoading(true);
    try {
      const res = await Api.postAction({ seat: humanSeat, action, amount });
      setState(res.state);

      // Always follow up by polling until it's our turn or the hand is over.
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

  // Prefer typed jam amount when provided by backend; fallback to sentinel
  const typedActions: AllowedAction[] = state?.allowed?.actions ?? [];
  const jamTotal = useMemo(
    () =>
      typedActions.find(
        (a) => a.type === "jam" && typeof a.amount === "number"
      )?.amount,
    [typedActions]
  );
  function jamAmount(): number {
    return typeof jamTotal === "number" ? jamTotal : 1_000_000_000;
  }

  // Dynamic verb for any sized action
  const currentSizedVerb = allowedCtx?.to_call === 0 ? "bet" : "raise";
  const sizedLabel = allowedCtx?.to_call === 0 ? "Bet" : "Raise";

  // Decision idx (best-effort)
  const decisionIdx =
    typeof (state as any)?.decision_idx === "number"
      ? (state as any).decision_idx
      : canAct
      ? 0
      : null;

  const coachShouldShow =
    coachEnabled &&
    canAct &&
    state &&
    state.street !== "preflop" &&
    decisionIdx !== null;

  // Dev util: copy raw state
  const copyState = async () => {
    if (!state) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(state, null, 2));
    } catch {
      // noop
    }
  };

  // Board extraction using structured board; show latest single turn/river card
  const flop: string[] = state?.board?.flop ?? [];
  const turnArr: string[] = state?.board?.turn ?? [];
  const riverArr: string[] = state?.board?.river ?? [];
  const turnCard: string | null =
    turnArr.length > 0 ? turnArr[turnArr.length - 1] : null;
  const riverCard: string | null =
    riverArr.length > 0 ? riverArr[riverArr.length - 1] : null;

  // Allowed buckets helpers. Only show actions explicitly provided by the server,
  // with a tiny defensive fallback for Fold when a call is required.
  const allowedBuckets = allowedCtx?.allowed_buckets ?? [];
  const showCheck = allowedBuckets.includes("check");
  const showCall = allowedBuckets.includes("call");
  // Defensive: if server omitted "fold" but to_call > 0, still show Fold.
  const foldListed = allowedBuckets.includes("fold");
  const showFold = foldListed || (!foldListed && (allowedCtx?.to_call ?? 0) > 0);
  const sizedLabels = allowedBuckets.filter((b) => /^\d+(?:\.\d+)?x$/.test(b));
  const showJam = allowedBuckets.includes("jam");

  return (
    <main className="min-h-screen p-6 bg-gray-50 relative">
      {/* Overlay shown when waiting for bots to act (prod mode). */}
      <WaitingOverlay show={botsAdvancing} message="Waiting for opponents…" />
      <div className="max-w-5xl mx-auto grid gap-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">NLH Trainer — Table</h1>
          <div className="flex items-center gap-3">
            {botsAdvancing && (
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
            {/* Table card */}
            <div className="rounded-2xl bg-white shadow p-4 space-y-2">
              <h2 className="font-semibold">Table</h2>
              <div className="text-sm text-gray-700">
                <div>Seats: {state.table.seats}</div>
                <div>
                  Blinds: {state.table.sb}/{state.table.bb}
                </div>
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

            {/* Players */}
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

            {/* Board (full-width) */}
            <div className="rounded-2xl bg-white shadow p-4 space-y-2 md:col-span-3">
              <h2 className="font-semibold">Board</h2>

              {/* [BOARD-LEGEND] — adds a tiny legend above the shared board row */}
              <div className="space-y-1">
                <div className="text-xs text-gray-500">Flop / Turn / River</div>
                <CommunityBoardRow flop={flop} turn={turnCard} river={riverCard} />
              </div>
              {/* [/BOARD-LEGEND] */}
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
                Allowed: {allowedBuckets.join(", ")}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {/* Fold */}
              {showFold && (
                <button
                  onClick={() => postAction("fold")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Fold
                </button>
              )}

              {/* Check */}
              {showCheck && (
                <button
                  onClick={() => postAction("check")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Check
                </button>
              )}

              {/* Call */}
              {showCall && (
                <button
                  onClick={() => postAction("call")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Call {allowedCtx.to_call}
                </button>
              )}

              {/* Quick open/raise sizes (use dynamic verb, from bucket labels) */}
              {sizedLabels.map((label) => {
                const amt = amountForOpenLabel(label);
                return (
                  <button
                    key={label}
                    onClick={() => postAction(currentSizedVerb, amt)}
                    className="rounded-xl bg-black text-white px-3 py-2 disabled:opacity-50"
                    disabled={loading}
                    title={`Total ${amt}`}
                  >
                    {sizedLabel} {label}
                  </button>
                );
              })}

              {/* Jam (use dynamic verb) — prefer typed amount when available */}
              {showJam && (
                <button
                  onClick={() => postAction(currentSizedVerb, jamAmount())}
                  className="rounded-xl bg-red-600 text-white px-3 py-2 disabled:opacity-50"
                  disabled={loading}
                >
                  Jam
                </button>
              )}
            </div>

            {/* Custom sized action uses dynamic verb */}
            <CustomSized
              disabled={loading}
              verb={currentSizedVerb}
              onSubmit={(amt) => postAction(currentSizedVerb, amt)}
            />
          </div>
        )}

        {/* Coach Panel (postflop, human turn only) */}
        {coachShouldShow && (
          <CoachPanel
            enabled={true}
            handId={handId}
            idx={decisionIdx}
            street={state?.street}
          />
        )}

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

function CustomSized({
  disabled,
  verb,
  onSubmit,
}: {
  disabled?: boolean;
  verb: "bet" | "raise";
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
        {verb === "bet" ? "Bet" : "Raise"} (custom)
      </button>
    </form>
  );
}
