// frontend/pages/table.tsx
// Dark-mode table page for playing vs the bot with guidance overlay.
//
// This page shows a basic poker table with hero and opponent seats,
// board cards, action buttons and preset bet sizes. It also wires in
// unified coach advice (preflop charts, solver/equity postflop) via
// the DecisionHelpOverlay hook, but renders the advice inline in a
// "Coach" panel instead of as a separate overlay. Stacks are extracted
// using the getPlayerStackFromState helper so that chips-behind display is
// consistent with backend semantics.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Api } from '../lib/api';
import type {
  AllowedContext,
  HandState,
  Actor,
} from '../lib/types/hand';
import { WaitingOverlay } from '../components/WaitingOverlay';
import { BoardRow as CommunityBoardRow } from '../components/common/Cards';
import {
  formatStack,
  getPlayerStackFromState,
  heroStackFromMaps,
  computeEffectiveStack,
} from '../utils/stack';
import { amountForPercentLabel } from '../utils/potSizing';
import { useDecisionOverlay } from '../hooks/useDecisionOverlay';
import { mapCoachToAction } from '../utils/coachMapping';
import type { DecisionContext } from '../types/decision';

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

  // Make sure the user can see the button
  const buttonSeat = state?.table?.button ?? null;

  // Pending bet/raise amount that presets/custom input write into.
  // The Bet/Raise button uses this value when clicked.
  const [pendingAmount, setPendingAmount] = useState<number | null>(null);
  const [customAmount, setCustomAmount] = useState<string>('');

  const humanSeat =
    typeof window !== 'undefined'
      ? parseInt(localStorage.getItem(HUMAN_SEAT_KEY) || '0', 10)
      : 0;

  const bb = useMemo(() => state?.table?.bb ?? 100, [state]);

  // Always rely on the server-reported pot_total. The backend exposes
  // a cumulative pot_total that should be trusted over any derived or
  // legacy fields.
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

  const toCall = allowedCtx?.to_call ?? 0;

  // Dynamic verb for any sized action
  const currentSizedVerb: 'bet' | 'raise' =
    allowedCtx?.to_call === 0 ? 'bet' : 'raise';
  const sizedLabel = allowedCtx?.to_call === 0 ? 'Bet' : 'Raise';

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
      // Clear pending amount when the full state refreshes (new decision / hand).
      setPendingAmount(null);
      setCustomAmount('');
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
      // Clear any previous sizing after we act
      setPendingAmount(null);
      setCustomAmount('');
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

  // Opponent cards (revealed only at showdown; backend masks as "XX" before that)
  const opponentCards: string[] = useMemo(() => {
    const cards = opponentPlayer?.hole_cards;
    if (!Array.isArray(cards)) return [];
    if (cards.length !== 2) return [];
    if (cards[0] === 'XX' || cards[1] === 'XX') return [];
    return [...cards];
  }, [opponentPlayer]);

  // Extract stacks via helper. Fallback to null when unavailable.
  const heroStack: number | null = useMemo(() => {
    return getPlayerStackFromState(heroPlayer, state);
  }, [heroPlayer, state]);
  const opponentStack: number | null = useMemo(() => {
    return getPlayerStackFromState(opponentPlayer, state);
  }, [opponentPlayer, state]);

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

  // Size presets:
  // - preflop: use X-multipliers from allowedBuckets
  // - postflop: fixed % of pot labels
  const sizedLabels = useMemo(() => {
    if (!state) return [] as string[];
    const street = (state.street ?? 'preflop').toLowerCase();

    if (street === 'preflop') {
      // Preflop: use X-multipliers that the engine says are legal
      // (e.g. "2.2x", "2.5x", "3.0x").
      return allowedBuckets.filter((b) => MULTIPLIER_LABEL_RE.test(b));
    }

    // Postflop: use the percent-of-pot labels that are actually allowed
    // at this node, e.g. ["25%", "40%", "67%"]. This keeps the buttons
    // in sync with the buckets we give to TexasSolver / the coach.
    const percents = allowedBuckets.filter((b) => PERCENT_LABEL_RE.test(b));

    if (percents.length > 0) {
      return percents;
    }

    // Fallback for odd states: show a sensible default grid.
    return ['25%', '40%', '67%'];
  }, [allowedBuckets, state]);


  // ------------------- Decision context + advice overlay --------------------
  const decisionContext: DecisionContext | null = useMemo(() => {
    if (!state) return null;
    // Unique decision id within the hand; may be null before hero acts.
    const idx = typeof decisionIdx === 'number' ? decisionIdx : null;
    const street = state.street ?? null;
    const toCallLocal = allowedCtx?.to_call ?? 0;
    // Flattened board cards
    const board: string[] = [];
    board.push(...flop);
    if (turnCard) board.push(turnCard);
    if (riverCard) board.push(riverCard);
    // Known opponent hands (if revealed)
    const knownHands: Record<number, string[]> = {};
    if (Array.isArray(state.players)) {
      state.players.forEach((p: any) => {
        if (p?.seat == null || p.seat === humanSeat) return;
        const cards = p.hole_cards;
        if (Array.isArray(cards) && cards.length === 2) {
          if (cards[0] !== 'XX' && cards[1] !== 'XX') {
            knownHands[p.seat] = [...cards];
          }
        }
      });
    }
    const playerCount = Array.isArray(state.players) ? state.players.length : 0;
    // Attempt to extract seat-level stack maps.
    let seatStacks: any = undefined;
    const stackCandidates = [
      (state as any).stack_by_seat,
      (state as any).stacks_by_seat,
      (state as any).stacks_after,
      (state as any).stacks,
      (state as any).table?.stacks,
      (state as any).table?.stacks_after,
      (state as any).table?.stack_by_seat,
      (state as any).table?.stacks_by_seat,
    ];
    for (const m of stackCandidates) {
      if (m && typeof m === 'object') {
        seatStacks = m;
        break;
      }
    }
    let seatCommitted: any = undefined;
    const committedCandidates = [
      (state as any).committed_by_seat,
      (state as any).seat_committed,
      (state as any).committed,
      (state as any).table?.committed_by_seat,
      (state as any).table?.committed,
    ];
    for (const m of committedCandidates) {
      if (m && typeof m === 'object') {
        seatCommitted = m;
        break;
      }
    }
    // Derive hero stack from seat map if possible; otherwise fall back
    // to our computed heroStack. Use null rather than undefined so
    // context keys exist for optional fields.
    let heroStackCtx: number | null = heroStack;
    if (seatStacks) {
      const st = heroStackFromMaps(humanSeat as any, seatStacks, seatCommitted);
      if (st !== null) heroStackCtx = st;
    }
    // Compute effective stack vs main opponent.
    let effectiveStack: number | null = null;
    if (seatStacks) {
      const eff = computeEffectiveStack(humanSeat as any, seatStacks, seatCommitted);
      effectiveStack = eff?.effectiveStack ?? null;
    }
    const ctx: DecisionContext = {
      handId: handId,
      idx: idx,
      street: street,
      heroSeat: humanSeat,
      pot: pot,
      toCall: toCallLocal,
      heroCards: heroCards,
      board: board,
      knownHandsBySeat: knownHands,
      playerCount: playerCount,
    };
    if (heroStackCtx != null) ctx.heroStack = heroStackCtx;
    if (effectiveStack != null) ctx.effectiveStack = effectiveStack;
    if (seatStacks) ctx.stackBySeat = seatStacks;
    if (seatCommitted) ctx.committedBySeat = seatCommitted;
    return ctx;
  }, [
    state,
    decisionIdx,
    allowedCtx,
    flop,
    turnCard,
    riverCard,
    heroStack,
    handId,
    humanSeat,
    pot,
    heroCards,
  ]);

  // Use the coach hook, but we'll render the advice inline instead of
  // as a separate floating overlay.
  const overlay: any = useDecisionOverlay(decisionContext, true);

  const coachAdvice: any = overlay?.advice;

  // Derive a recommended action key from the coach advice. Use the
  // available presets so that sized actions (e.g. 2.5x, 33%) are matched
  // against actual buttons. If no recommendation exists, returns null.
  const recommendedActionKey: string | null = useMemo(() => {
    if (!decisionContext) return null;
    if (!coachAdvice || coachAdvice.status !== 'ok' || !coachAdvice.data) return null;
    const rec = coachAdvice.data.recommendation;
    const bucket = rec?.bucket ?? rec?.primary_action;
    if (!bucket) return null;
    const localToCall = allowedCtx?.to_call ?? 0;
    return mapCoachToAction(bucket, localToCall, sizedLabels);
  }, [coachAdvice, allowedCtx, sizedLabels, decisionContext]);

  // Simple showdown summary banner
  const showdownSummary: string | null = useMemo(() => {
    if (!state) return null;
    const street = (state.street ?? '').toLowerCase();
    if (street !== 'showdown') return null;
    const la: any = state.last_action ?? null;
    const rawType = (la && (la.type ?? la.action)) || null;
    const t =
      typeof rawType === 'string' ? rawType.toLowerCase() : null;
    const seat = typeof la?.seat === 'number' ? la.seat : null;

    if (t === 'fold' && seat != null) {
      if (seat === humanSeat) {
        return 'Opponent wins (you folded).';
      }
      return 'You win (opponent folded).';
    }
    return 'Showdown complete.';
  }, [state, humanSeat]);

  // High-level coach recommendation summary for the inline coach panel
  const coachRecommendation = useMemo(() => {
    if (!coachAdvice || coachAdvice.status !== 'ok' || !coachAdvice.data) {
      return null;
    }
    const data: any = coachAdvice.data;
    const rec: any = data.recommendation ?? data.primary ?? null;
    if (!rec) return null;
    const action: string | null =
      rec.bucket ?? rec.primary_action ?? rec.action ?? null;
    const confidence: number | null =
      typeof rec.confidence === 'number' ? rec.confidence : null;
    const evDiff: number | null =
      typeof rec.ev_diff_bb === 'number' ? rec.ev_diff_bb : null;
    return { action, confidence, evDiff };
  }, [coachAdvice]);

  const isRaiseRecommended =
    !!recommendedActionKey &&
    !['fold', 'call', 'check'].includes(recommendedActionKey);

  // Dev util: copy raw state
  const copyState = async () => {
    if (!state) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(state, null, 2));
    } catch {
      // noop
    }
  };

  // Handle "use custom bet" – this just updates the pendingAmount,
  // it does NOT send the action. The main Bet/Raise button will use
  // pendingAmount when clicked.
  function applyCustomAmount() {
    const n = parseInt(customAmount, 10);
    if (!Number.isNaN(n) && n > 0) {
      setPendingAmount(n);
      setCustomAmount(String(n));
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50 relative">
      {/* Overlay shown when waiting for bots to act */}
      <WaitingOverlay show={botsAdvancing} message="Waiting for opponents…" />

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h1 className="text-xl font-semibold tracking-wide">
              Poker — Info
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              {state
                ? `${state.table.sb}/${state.table.bb} · ${state.table.seats} seats · BTN ${state.table.button}`
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
          {showdownSummary && (
            <span>
              Result:{' '}
              <span className="font-medium">
                {showdownSummary}
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
                <div className="flex gap-2 text-lg">
                  {opponentCards.length === 2 ? (
                    <>
                      <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-100">
                        {opponentCards[0]}
                      </span>
                      <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-100">
                        {opponentCards[1]}
                      </span>
                    </>
                  ) : (
                    <span className="inline-block rounded-md bg-slate-800 px-3 py-1 text-slate-300 text-sm">
                      Cards hidden
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1">
                  <span>
                    Seat {opponentPlayer ? opponentPlayer.seat : '—'}
                  </span>
                  {buttonSeat != null &&
                    opponentPlayer &&
                    opponentPlayer.seat === buttonSeat && (
                      <span className="px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/50 text-[10px] uppercase tracking-wide">
                        BTN
                      </span>
                  )}
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
                <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1">
                  <span>Seat {humanSeat} (You)</span>
                  {buttonSeat != null && humanSeat === buttonSeat && (
                    <span className="px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/50 text-[10px] uppercase tracking-wide">
                      BTN
                    </span>
                  )}
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

          {/* Bottom row: coach info + action panel */}
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1.7fr)]">
            {/* Coach panel (inline guidance) */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold tracking-wide text-slate-100">
                  Coach
                </h2>
                {coachAdvice && (
                  <span className="text-[11px] px-2 py-1 rounded-full border border-slate-700 text-slate-300 bg-slate-950/40">
                    {coachAdvice.status === 'loading'
                      ? 'Loading…'
                      : coachAdvice.status === 'ok'
                      ? 'Ready'
                      : coachAdvice.status === 'disabled'
                      ? 'Disabled'
                      : coachAdvice.status === 'not_found'
                      ? 'Not available'
                      : coachAdvice.status === 'unavailable'
                      ? 'Unavailable'
                      : 'Idle'}
                  </span>
                )}

              </div>
              {!decisionContext && (
                <p className="text-xs text-slate-500 mt-1">
                  No active decision yet. Start a hand and wait for your turn.
                </p>
              )}
              {decisionContext && (
                <div className="text-xs text-slate-400 space-y-1 mt-1">
                  <p>
                    Street{' '}
                    <span className="font-medium text-slate-200">
                      {decisionContext.street ?? '—'}
                    </span>{' '}
                    · Pot{' '}
                    <span className="font-medium text-slate-200">
                      {decisionContext.pot}
                    </span>
                  </p>
                  {coachRecommendation?.action && (
                    <p>
                      Recommended:{' '}
                      <span className="font-semibold text-emerald-300">
                        {coachRecommendation.action}
                      </span>
                      {coachRecommendation.evDiff != null && (
                        <span className="ml-1 text-[11px] text-emerald-200/80">
                          (~{coachRecommendation.evDiff.toFixed(2)} bb)
                        </span>
                      )}
                    </p>
                  )}
                  {coachAdvice?.status === 'ok' && !coachRecommendation && (
                    <p className="text-[11px] text-slate-500">
                      Coach ready but no explicit recommendation for this spot.
                    </p>
                  )}
                  {coachAdvice?.error && coachAdvice.status !== 'ok' && (
                    <p className="text-[11px] text-rose-300">
                      {String(coachAdvice.error)}
                    </p>
                  )}

                  {heroStack != null && (
                    <p>
                      Hero stack:{' '}
                      <span className="font-medium text-slate-200">
                        {formatStack(heroStack, bb)}
                      </span>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Action / betting panel */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold tracking-wide text-slate-100">
                  Preset Bet Sizes
                </h2>
                <div className="text-xs text-slate-400">
                  To call:{' '}
                  <span className="font-medium">
                    {toCall}
                  </span>
                </div>
              </div>

              {canAct && allowedCtx && state ? (
                <>
                  {/* Size presets row (just selects a size, does NOT send the action) */}
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
                            // back to other bounds.
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

                          const isSelected =
                            pendingAmount != null &&
                            amt != null &&
                            pendingAmount === amt;

                          return (
                            <button
                              key={label}
                              onClick={() => {
                                if (amt != null) {
                                  setPendingAmount(amt);
                                  setCustomAmount(String(amt));
                                }
                              }}
                              className={`rounded-2xl px-3 py-2 text-xs font-medium bg-slate-800 border border-slate-600 text-slate-50 disabled:opacity-40 ${
                                recommendedActionKey === label
                                  ? 'border-amber-400 bg-amber-900 text-amber-200'
                                  : ''
                              } ${
                                isSelected
                                  ? 'ring-1 ring-emerald-400/70'
                                  : ''
                              }`}
                              disabled={loading || amt == null}
                              title={title}
                            >
                              {label}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Custom bet field (sets pendingAmount, does not send action) */}
                  <div className="space-y-1">
                    <div className="text-[11px] text-slate-400">
                      Custom bet size
                    </div>
                    <form
                      className="flex items-center gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        applyCustomAmount();
                      }}
                    >
                      <input
                        type="number"
                        min={1}
                        placeholder="Total chips"
                        className="flex-1 rounded-lg border border-slate-600 bg-slate-950 px-3 py-1.5 text-xs text-slate-50 placeholder:text-slate-500"
                        value={customAmount}
                        onChange={(e) => setCustomAmount(e.target.value)}
                      />
                      <button
                        type="submit"
                        className="rounded-xl border border-slate-600 px-3 py-1.5 text-xs text-slate-50 disabled:opacity-50"
                        disabled={loading}
                      >
                        Use size
                      </button>
                    </form>
                    {pendingAmount != null && (
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Selected total:{' '}
                        <span className="font-medium text-slate-100">
                          {pendingAmount}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Big primary action buttons */}
                  <div className="flex flex-wrap gap-3 pt-1">
                    {/* Fold */}
                    {showFold && (
                      <button
                        onClick={() => postAction('fold')}
                        className={`flex-1 min-w-[90px] rounded-2xl px-4 py-3 text-sm font-semibold border border-rose-700/70 bg-gradient-to-br from-rose-900 to-rose-800 text-rose-50 shadow-sm disabled:opacity-50 ${
                          recommendedActionKey === 'fold'
                            ? 'border-amber-400 bg-amber-900 text-amber-200'
                            : ''
                        }`}
                        disabled={loading}
                      >
                        Fold
                      </button>
                    )}

                    {/* Check / Call */}
                    {(showCheck || showCall) && (
                      <button
                        onClick={() => postAction(showCall ? 'call' : 'check')}
                        className={`flex-1 min-w-[110px] rounded-2xl px-4 py-3 text-sm font-semibold border border-slate-600 bg-slate-800 text-slate-50 shadow-sm disabled:opacity-50 ${
                          recommendedActionKey === (showCall ? 'call' : 'check')
                            ? 'border-amber-400 bg-amber-900 text-amber-200'
                            : ''
                        }`}
                        disabled={loading}
                      >
                        {showCall
                          ? `Call ${toCall}`
                          : 'Check'}
                      </button>
                    )}

                    {/* Bet/Raise uses the currently selected pendingAmount */}
                    <button
                      onClick={() => {
                        if (pendingAmount != null) {
                          postAction(currentSizedVerb, pendingAmount);
                        }
                      }}
                      className={`flex-1 min-w-[110px] rounded-2xl px-4 py-3 text-sm font-semibold border border-emerald-600 bg-gradient-to-br from-emerald-900 to-emerald-700 text-emerald-50 shadow-sm disabled:opacity-50 ${
                        isRaiseRecommended
                          ? 'border-amber-400 bg-amber-900 text-amber-200'
                          : ''
                      }`}
                      disabled={
                        loading ||
                        pendingAmount == null ||
                        !allowedCtx
                      }
                    >
                      {sizedLabel}
                      {pendingAmount != null ? ` ${pendingAmount}` : ''}
                    </button>
                  </div>
                </>
              ) : (
                <div className="text-xs text-slate-400">
                  Waiting for opponents or no action available.
                </div>
              )}
            </div>
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
