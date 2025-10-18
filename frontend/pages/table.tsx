// frontend/pages/table.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { Api } from "../lib/api";

type Actor = { seat: number; to_call: number; allowed_buckets: string[] } | null;

export default function TablePage() {
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState<any>(null);
  const [actor, setActor] = useState<Actor>(null);
  const [err, setErr] = useState<string | null>(null);
  const humanSeat =
    typeof window !== "undefined" ? parseInt(localStorage.getItem("humanSeat") || "0", 10) : 0;

  const bb = useMemo(() => state?.table?.bb ?? 100, [state]);

  const refresh = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const r = await Api.getState();
      setState(r.state);
      setActor(r.actor ?? null);
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
      await Api.startHand();
      await refresh();
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  async function postAction(action: string, amount?: number) {
    if (!actor) return;
    setErr(null);
    setLoading(true);
    try {
      const res = await Api.postAction({ seat: humanSeat, action, amount });
      setState(res.state);
      // After bet/raise, the backend returns pre-bot state so snapping is visible.
      // After check/call, backend auto-advances bots and returns post-bot state.
      const next = await Api.getState();
      setState(next.state);
      setActor(next.actor ?? null);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // Preflop open helpers (for HU SB open labels 2.2x/2.5x/3.0x)
  function amountForOpenLabel(label: string): number | undefined {
    const m = label.match(/^(\d+(?:\.\d+)?)x$/);
    if (!m) return undefined;
    const mult = parseFloat(m[1]);
    // Use exact target (engine will snap anyway)
    return Math.round(mult * bb);
  }

  // Jam uses a sentinel large number; engine will cap/snap appropriately.
  function jamAmount(): number {
    return 1_000_000_000;
  }

  const canAct = actor && actor.seat === humanSeat;

  return (
    <main className="min-h-screen p-6 bg-gray-50">
      <div className="max-w-5xl mx-auto grid gap-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">NLH Trainer — Table</h1>
          <div className="flex items-center gap-3">
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
                {"pot_total" in state && <div>Pot: {state.pot_total}</div>}
                <div className="text-gray-500 text-xs">Seed: {state.deck_seed}</div>
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
        {canAct && actor && state && (
          <div className="rounded-2xl bg-white shadow p-4 space-y-4">
            <h2 className="font-semibold">Your Action</h2>
            <div className="text-sm text-gray-700">
              <div>To call: {actor.to_call}</div>
              <div className="text-xs text-gray-500">
                Allowed: {actor.allowed_buckets.join(", ")}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {/* If to_call == 0, "check" is legal */}
              {actor.to_call === 0 && (
                <button
                  onClick={() => postAction("check")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Check
                </button>
              )}

              {/* If to_call > 0, "call" is legal */}
              {actor.to_call > 0 && actor.allowed_buckets.includes("call") && (
                <button
                  onClick={() => postAction("call")}
                  className="rounded-xl border px-3 py-2"
                  disabled={loading}
                >
                  Call {actor.to_call}
                </button>
              )}

              {/* Quick open sizes for HU SB preflop open */}
              {actor.allowed_buckets
                .filter((b) => /^\d+(\.\d+)?x$/.test(b))
                .map((label) => {
                  const amt = amountForOpenLabel(label);
                  return (
                    <button
                      key={label}
                      onClick={() => postAction("raise", amt)}
                      className="rounded-xl bg-black text-white px-3 py-2 disabled:opacity-50"
                      disabled={loading}
                      title={`Total ${amt}`}
                    >
                      Raise {label}
                    </button>
                  );
                })}

              {/* Jam */}
              {actor.allowed_buckets.includes("jam") && (
                <button
                  onClick={() => postAction("raise", jamAmount())}
                  className="rounded-xl bg-red-600 text-white px-3 py-2 disabled:opacity-50"
                  disabled={loading}
                >
                  Jam
                </button>
              )}
            </div>

            {/* Custom raise for other scenarios (postflop, facing raise, etc.) */}
            <CustomRaise
              disabled={loading}
              onSubmit={(amt) => postAction("raise", amt)}
            />
          </div>
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
