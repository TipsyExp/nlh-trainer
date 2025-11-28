// frontend/pages/table.tsx
// Minimal dark-mode table page for playing vs the bot.
//
// - Shows basic table info, board, hero and opponent.
// - Provides action buttons based on allowed_buckets.
// - No coach overlay, no CoachPanel, no advice wiring.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Api } from '../lib/api';
import type {
  AllowedContext,
  HandState,
  Actor,
  AllowedAction,
} from '../lib/types/hand';
import { WaitingOverlay } from '../components/WaitingOverlay';
import { BoardRow as CommunityBoardRow } from '../components/common/Cards';
import { formatStack } from '../utils/stack';
import { amountForPercentLabel } from '../utils/potSizing';
import SnapshotInspector from '../dev/SnapshotInspector';

// Gate dev-only /api/hand/auto. Default is false unless explicitly enabled.
const AUTO_HAND_ENABLED = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.NEXT_PUBLIC_ENABLE_HAND_AUTO || '').toLowerCase()
);
const DEV_TOOLS = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.NEXT_PUBLIC_DEV_TOOLS || '').toLowerCase()
);

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

// X-multiplier labels, e.g. "2.2x", "3x"
const MULTIPLIER_LABEL_RE = /^(\d+(?:\.\d+)?)x$/;
// % labels, e.g. "33%", "50%", "75%"
const PERCENT_LABEL_RE = /^(\d+(?:\.\d+)?)%$/;

export default function TablePage() {
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState<HandState | null>(null);
  const [actor, setActor] = useState<Actor | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [botsAdvancing, setBotsAdvancing] = useState(false);

  const HUMAN_SEAT_KEY = 'humanSeat';

  const [handId, setHandId] = useState<string | null>(null);

  const humanSeat =
    typeof window !== 'undefined'
      ? parseInt(localStorage.getItem(HUMAN_SEAT_KEY) || '0', 10)
      : 0;

  const bb = useMemo(() => state?.table?.bb ?? 100, [state]);

  // Always rely on the server‑reported pot_total. The backend exposes
  // a cumulative pot_total that should be trusted over any derived or
  // legacy fields (pot_after, pot). Falling back to those legacy fields
  // caused out‑of‑sync values and huge numbers when pot percentage sizing
  // mis‑computed.
  const pot = useMemo(() => state?.pot_total ?? 0, [state]);

  // Prefer state.allowed/to_act if present; fallback to legacy actor
  const allowedCtx: AllowedContext | null = useMemo(() => {
    if (!state) return null;
    if (state.allowed && typeof state.allowed.to_call === 'number') {
      return state.allowed;
    }
    if (actor) {
      return {
        to_call: actor.to_call,
        min_raise: actor.min_raise ?? Math.max(100, bb),
        allowed_buckets: actor.allowed_buckets || [],
      };
    }
    return null;
  }, [state, actor, bb]);

  const allowedBuckets = useMemo(
    () => allowedCtx?.allowed_buckets ?? [],
    [allowedCtx]
  );

  const toActSeat = state?.to_act ?? actor?.seat ?? null;
  const canAct = toActSeat === humanSeat;

  // Dynamic verb for any sized action
  const currentSizedVerb: 'bet' | 'raise' =
    allowedCtx?.to_call === 0 ? 'bet' : 'raise';
  const sizedLabel = allowedCtx?.to_call === 0 ? 'Bet' : 'Raise';

  // Typed actions, used for jam sizing when backend provides it.
  const typedActions: AllowedAction[] = state?.allowed?.actions ?? [];

  // If backend gives us a jam action with an explicit amount, use it.
  // Otherwise we will call "jam" without an amount and let the server decide.
  const jamAction = useMemo(
    () => typedActions.find((a) => a.type === 'jam'),
    [typedActions]
  );

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
        const finished = snap?.state?.street === 'showdown';
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
      await pollUntilSettled(humanSeat);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // Preflop open helpers (X × BB)
  function amountForOpenLabel(label: string): number | undefined {
    const m = label.match(MULTIPLIER_LABEL_RE);
    if (!m) return undefined;
    const mult = parseFloat(m[1]);
    return Math.round(mult * bb);
  }

  function handleJam() {
    if (!allowedCtx) return;

    // Prefer the explicit "jam" verb if it's in allowed_buckets; otherwise
    // fall back to the current sized verb (bet/raise) just in case.
    const verb = allowedCtx.allowed_buckets?.includes('jam')
      ? 'jam'
      : currentSizedVerb;

    const amount =
      jamAction && typeof jamAction.amount === 'number'
        ? jamAction.amount
        : undefined;

    // Do NOT invent a giant fallback like 1e12; if the backend needs an
    // explicit amount it should give us one.
    postAction(verb, amount);
  }

  // Decision idx (best-effort; still handy for debugging)
  const decisionIdx =
    typeof (state as any)?.decision_idx === 'number'
      ? (state as any).decision_idx
      : canAct
      ? 0
      : null;

  // Hero / opponent lookup
  const heroPlayer: any | null = useMemo(
    () => state?.players?.find((p: any) => p.seat === humanSeat) ?? null,
    [state?.players, humanSeat]
  );
  const opponentPlayer: any | null = useMemo(
    () => state?.players?.find((p: any) => p.seat !== humanSeat) ?? null,
    [state?.players, humanSeat]
  );

  const heroCards: string[] = useMemo(
    () => (heroPlayer?.hole_cards ? [...heroPlayer.hole_cards] : []),
    [heroPlayer]
  );

  const heroStack: number | null = useMemo(() => {
    if (!heroPlayer) return null;
    const raw =
      (heroPlayer as any).stack_after ??
      (heroPlayer as any).stack ??
      (heroPlayer as any).chips ??
      null;
    return typeof raw === 'number' ? raw : null;
  }, [heroPlayer]);

  const opponentStack: number | null = useMemo(() => {
    if (!opponentPlayer) return null;
    const raw =
      (opponentPlayer as any).stack_after ??
      (opponentPlayer as any).stack ??
      (opponentPlayer as any).chips ??
      null;
    return typeof raw === 'number' ? raw : null;
  }, [opponentPlayer]);

  // Board extraction
  const flop: string[] = state?.board?.flop ?? [];
  const turnArr: string[] = state?.board?.turn ?? [];
  const riverArr: string[] = state?.board?.river ?? [];
  const turnCard: string | null =
    turnArr.length > 0 ? turnArr[turnArr.length - 1] : null;
  const riverCard: string | null =
    riverArr.length > 0 ? riverArr[riverArr.length - 1] : null;

  // Action visibility flags
  const showCheck = allowedBuckets.includes('check');
  const showCall = allowedBuckets.includes('call');
  const foldListed = allowedBuckets.includes('fold');
  const showFold =
    foldListed || (!foldListed && (allowedCtx?.to_call ?? 0) > 0);
  const showJam = allowedBuckets.includes('jam');

  // Size presets:
  // - preflop: use X-multipliers from allowedBuckets
  // - postflop: fixed % of pot labels
  const sizedLabels = useMemo(() => {
    if (!state) return [];
    const street = state.street ?? 'preflop';
    if (street.toLowerCase() === 'preflop') {
      return allowedBuckets.filter((b) => MULTIPLIER_LABEL_RE.test(b));
    }
    // postflop: fixed percent options
    return ['33%', '50%', '75%', '100%'];
  }, [allowedBuckets, state]);

  // Dev util: copy raw state
  const copyState = async () => {
    if (!state) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(state, null, 2));
    } catch {
      // noop
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50 relative">
      {/* Overlay shown when waiting for bots to act */}
      <WaitingOverlay show={botsAdvancing} message="Waiting for opponents…" />

      {DEV_TOOLS && <SnapshotInspector />}

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h1 className="text-xl font-semibold tracking-wide">
              Poker — Info
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              {state
                ? `${state.table.sb}/${state.table.bb} · ${
                    state.table.seats
                  } seats · BTN ${state.table.button}`
                : 'No session active'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {botsAdvancing && (
              <span className="text-[11px] px-2 py-1 rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/40">
                Bots thinking…
              </span>
            )}
            <button
              onClick={onStartHand}
              className="rounded-xl bg-emerald-500 text-slate-950 px-4 py-2 text-sm font-medium disabled:opacity-50"
              disabled={loading}
            >
              {loading ? 'Working…' : 'Start Hand'}
            </button>
            <button
              onClick={refresh}
              className="rounded-xl border border-slate-600 px-4 py-2 text-sm text-slate-100 disabled:opacity-50"
              disabled={loading}
            >
              Refresh
            </button>
            {DEV_TOOLS && (
              <button
                onClick={copyState}
                className="rounded-xl border border-slate-600 px-3 py-2 text-[11px] text-slate-200 disabled:opacity-50"
                disabled={!state}
                title="Copy /api/hand/state JSON"
              >
                Copy state
              </button>
            )}
          </div>
        </header>

        {/* Error message */}
        {err && (
          <div className="rounded-xl border border-rose-600 bg-rose-950/60 text-rose-100 px-3 py-2 text-sm">
            {err}
          </div>
        )}

        {/* Table info strip */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-2 text-[11px] flex flex-wrap gap-x-4 gap-y-1">
          <span>
            Street:{' '}
            <span className="font-medium">
              {state?.street ?? '—'}
            </span>
          </span>
          <span>
            Pot:{' '}
            <span className="font-medium">
              {pot}
            </span>
          </span>
          {handId && (
            <span>
              Hand:{' '}
              <span className="font-mono text-slate-300">
                {handId}
              </span>
            </span>
          )}
          {typeof decisionIdx === 'number' && (
            <span>
              Decision:{' '}
              <span className="font-medium">
                {decisionIdx}
              </span>
            </span>
          )}
          <span>
            Hero seat:{' '}
            <span className="font-medium">
              {humanSeat}
            </span>
          </span>
          {heroStack != null && (
            <span>
              Hero stack:{' '}
              <span className="font-medium">
                {formatStack(heroStack, bb)}
              </span>
            </span>
          )}
        </section>

        {/* Main table view */}
        <section className="grid gap-4 lg:grid-rows-[1fr_auto]">
          {/* Central table */}
          <div className="rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950 px-4 py-5 flex flex-col gap-6">
            {/* Opponent */}
            <div className="flex justify-center">
              <div className="inline-flex flex-col items-center gap-2 px-4 py-3 rounded-2xl bg-slate-900/80 border border-slate-700 shadow-sm">
                <div className="text-xs uppercase tracking-wider text-slate-400">
                  Opponent
                </div>
                <div className="flex gap-1 text-lg">
                  <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-300 text-sm">
                    Cards hidden
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Seat{' '}
                  {opponentPlayer ? opponentPlayer.seat : '—'}
                </div>
                <div className="text-xs text-slate-300">
                  Stack:{' '}
                  {opponentStack != null
                    ? formatStack(opponentStack, bb)
                    : '—'}
                </div>
              </div>
            </div>

            {/* Board */}
            <div className="flex flex-col items-center gap-2">
              <div className="text-xs uppercase tracking-widest text-slate-400">
                Board · Pot {pot}
              </div>
              <CommunityBoardRow
                flop={flop}
                turn={turnCard}
                river={riverCard}
              />
            </div>

            {/* Hero */}
            <div className="flex justify-center">
              <div className="inline-flex flex-col items-center gap-2 px-4 py-3 rounded-2xl bg-slate-900/80 border border-slate-700 shadow-sm">
                <div className="text-xs uppercase tracking-wider text-slate-400">
                  Player
                </div>
                <div className="flex gap-2 text-lg">
                  {heroCards.length === 2 ? (
                    <>
                      <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-100">
                        {heroCards[0]}
                      </span>
                      <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-100">
                        {heroCards[1]}
                      </span>
                    </>
                  ) : (
                    <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-300 text-sm">
                      Cards unknown
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Seat {humanSeat} (You)
                </div>
                <div className="text-xs text-slate-300">
                  Stack:{' '}
                  {heroStack != null
                    ? formatStack(heroStack, bb)
                    : '—'}
                </div>
              </div>
            </div>
          </div>

          {/* Action panel */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold tracking-wide text-slate-100">
                Preset Bet Sizes
              </h2>
              <div className="text-xs text-slate-400">
                To call:{' '}
                <span className="font-medium">
                  {allowedCtx?.to_call ?? 0}
                </span>
              </div>
            </div>

            {canAct && allowedCtx && state ? (
              <>
                {/* Big primary buttons */}
                <div className="flex flex-wrap gap-3">
                  {/* Fold */}
                  {showFold && (
                    <button
                      onClick={() => postAction('fold')}
                      className="flex-1 min-w-[90px] rounded-2xl px-4 py-3 text-sm font-semibold border border-rose-700/70 bg-gradient-to-br from-rose-900 to-rose-800 text-rose-50 shadow-sm disabled:opacity-50"
                      disabled={loading}
                    >
                      Fold
                    </button>
                  )}

                  {/* Check / Call */}
                  {(showCheck || showCall) && (
                    <button
                      onClick={() =>
                        postAction(showCall ? 'call' : 'check')
                      }
                      className="flex-1 min-w-[110px] rounded-2xl px-4 py-3 text-sm font-semibold border border-slate-600 bg-slate-800 text-slate-50 shadow-sm disabled:opacity-50"
                      disabled={loading}
                    >
                      {showCall
                        ? `Call ${allowedCtx.to_call}`
                        : 'Check'}
                    </button>
                  )}

                  {/* Jam */}
                  {showJam && (
                    <button
                      onClick={handleJam}
                      className="flex-1 min-w-[90px] rounded-2xl px-4 py-3 text-sm font-semibold border border-red-700/70 bg-gradient-to-br from-red-900 to-red-800 text-red-50 shadow-sm disabled:opacity-50"
                      disabled={loading}
                    >
                      Jam
                    </button>
                  )}
                </div>

                {/* Size presets row */}
                {sizedLabels.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-slate-400">
                      Size presets
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {sizedLabels.map((label) => {
                        const isPercent = PERCENT_LABEL_RE.test(label);
                        let amt: number | null = null;
                        let title: string | undefined;

                        if (
                          isPercent &&
                          state.street &&
                          state.street.toLowerCase() !== 'preflop'
                        ) {
                          const toCall = allowedCtx.to_call ?? 0;
                          const minRaise = allowedCtx.min_raise ?? 0;
                          const maxRaiseRaw =
                            (allowedCtx as any).max_raise ??
                            (allowedCtx as any).max_bet ??
                            undefined;
                          const maxRaise =
                            typeof maxRaiseRaw === 'number'
                              ? maxRaiseRaw
                              : undefined;
                          // If heroStack is null, use a large sentinel so clamping falls
                          // back to other bounds. The helper will clamp to min/max and
                          // call if the stack is effectively infinite.
                          const heroStackForSizing =
                            heroStack != null
                              ? heroStack
                              : Number.MAX_SAFE_INTEGER;

                          const computed = amountForPercentLabel(
                            label,
                            pot,
                            toCall,
                            heroStackForSizing,
                            minRaise,
                            maxRaise
                          );
                          if (computed != null) {
                            amt = computed;
                            title = `~Total ${computed}`;
                          }
                        } else {
                          // Preflop X-multipliers
                          const maybeAmt = amountForOpenLabel(label);
                          if (typeof maybeAmt === 'number') {
                            amt = maybeAmt;
                            title = `Total ${maybeAmt}`;
                          }
                        }

                        return (
                          <button
                            key={label}
                            onClick={() => {
                              if (amt != null) {
                                postAction(currentSizedVerb, amt);
                              }
                            }}
                            className="rounded-2xl px-3 py-2 text-xs font-medium bg-slate-800 border border-slate-600 text-slate-50 disabled:opacity-40"
                            disabled={loading || amt == null}
                            title={title}
                          >
                            {sizedLabel} {label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Custom sized action */}
                <CustomSized
                  disabled={loading}
                  verb={currentSizedVerb}
                  onSubmit={(amt) =>
                    postAction(currentSizedVerb, amt)
                  }
                />
              </>
            ) : (
              <div className="text-xs text-slate-400">
                Waiting for opponents or no action available.
              </div>
            )}
          </div>
        </section>

        {/* Last action panel (debug) */}
        {state?.last_action && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 space-y-1">
            <h2 className="text-sm font-semibold text-slate-100">
              Last Action
            </h2>
            <pre className="text-[11px] bg-slate-950 rounded-xl p-3 overflow-auto text-slate-200">
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
  verb: 'bet' | 'raise';
  onSubmit: (amount: number) => void;
}) {
  const [val, setVal] = useState<string>('');

  return (
    <form
      className="flex items-center gap-2 mt-2"
      onSubmit={(e) => {
        e.preventDefault();
        const n = parseInt(val, 10);
        if (!Number.isNaN(n) && n > 0) {
          onSubmit(n);
          setVal('');
        }
      }}
    >
      <input
        type="number"
        min={1}
        placeholder="Custom total"
        className="rounded-lg border border-slate-600 bg-slate-950 px-3 py-1.5 text-xs text-slate-50 placeholder:text-slate-500"
        value={val}
        onChange={(e) => setVal(e.target.value)}
      />
      <button
        type="submit"
        className="rounded-xl border border-slate-600 px-3 py-1.5 text-xs text-slate-50 disabled:opacity-50"
        disabled={disabled}
      >
        {verb === 'bet' ? 'Bet' : 'Raise'} (custom)
      </button>
    </form>
  );
}