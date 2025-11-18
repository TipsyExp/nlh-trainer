// frontend/utils/equityParams.ts
// Helpers to assemble equity request bodies and signatures.
//
// The equity overlay needs to build structured inputs for the
// POST /api/equity endpoint based on the current decision context.
// This module contains helpers for preflop (range vs hand) and
// postflop (fixed hands) modes.  Each builder returns the request
// body along with a stable signature used for caching.  When
// circumstances make equity inappropriate (e.g. missing cards,
// unsupported number of players) the builder returns a reason so
// callers can skip the request entirely.

import type { DecisionContext } from '../types/decision';
import { stableHash } from './hash';
import { resolveVillainRange, type RangeOrigin } from './range';

// Default number of Monte Carlo iterations for preflop equity when not
// computing exact.  Can be overridden via NEXT_PUBLIC_EQUITY_ITERS_PREFLOP.
const DEFAULT_ITERS_PREFLOP = (() => {
  const raw = process.env.NEXT_PUBLIC_EQUITY_ITERS_PREFLOP;
  const n = raw ? parseInt(String(raw), 10) : NaN;
  return !Number.isNaN(n) && n > 0 ? n : 8000;
})();

export interface BuildResult {
  /** POST body for /api/equity. */
  body: Record<string, any> | null;
  /** Stable signature used for caching. */
  signature: string;
  /** Reason to skip equity (e.g. missing_hero, missing_range). */
  reasonIfSkipped?: string;
  /** Origin of villain range (default/random) for preflop context. */
  origin?: RangeOrigin;
  /** Mode used by the builder ('ranges' or 'hands'). */
  mode: 'ranges' | 'hands';
}

/**
 * Assemble a preflop equity request body.  Requires heroCards to be
 * present and a villain range to be available.  When conditions are
 * not met a reason is provided and body is null so the caller can
 * skip the call.  The signature incorporates only the relevant
 * inputs (hero hand and villain range) so that caching is robust
 * across re-renders.
 */
export function buildPreflopEquityBody(
  ctx: DecisionContext,
  opts?: { iters?: number; exact?: boolean }
): BuildResult {
  const result: BuildResult = {
    body: null,
    signature: '',
    mode: 'ranges',
  };
  const hero = ctx.heroCards;
  // Validate hero cards: must have exactly two cards known (no unknowns).
  if (!hero || hero.length !== 2) {
    result.reasonIfSkipped = 'missing_hero';
    return result;
  }
  const hasUnknown = hero.some((c) => !c || /\?/.test(c) || /X/.test(c));
  if (hasUnknown) {
    result.reasonIfSkipped = 'missing_hero';
    return result;
  }
  // Resolve villain range from environment.  Chart metadata is not available yet.
  const { range, origin } = resolveVillainRange(ctx);
  if (!range) {
    result.reasonIfSkipped = 'missing_range';
    return result;
  }
  const iters = opts?.iters ?? DEFAULT_ITERS_PREFLOP;
  const exact = !!opts?.exact;
  const players = [
    { hand: hero },
    { range },
  ];
  const board: string[] = [];
  const dead: string[] = [];
  const body = {
    players,
    board,
    dead,
    iters: exact ? undefined : iters,
    exact,
  };
  const signatureObj = { players, board, dead, exact, iters: body.iters ?? null };
  result.body = body;
  result.signature = stableHash(signatureObj);
  result.origin = origin;
  return result;
}

/**
 * Assemble a postflop equity request body.  Requires that all live
 * players have known hands (no unknown/masked cards) and that the
 * number of players does not exceed maxPlayers.  When conditions are
 * not met the call is skipped.
 */
export function buildPostflopEquityBody(
  ctx: DecisionContext,
  opts?: { iters?: number; exact?: boolean; maxPlayers?: number }
): BuildResult {
  const result: BuildResult = {
    body: null,
    signature: '',
    mode: 'hands',
  };
  const hero = ctx.heroCards;
  if (!hero || hero.length !== 2 || hero.some((c) => !c || /\?/.test(c) || /X/.test(c))) {
    result.reasonIfSkipped = 'missing_hero';
    return result;
  }
  const known = ctx.knownHandsBySeat || {};
  const players: Array<{ hand: string[] }> = [];
  // First add hero
  players.push({ hand: hero });
  // Add opponents with fully known hands
  for (const seatStr of Object.keys(known)) {
    const seat = seatStr as any;
    const cards = known[seat as any];
    if (!cards || cards.length !== 2) {
      result.reasonIfSkipped = 'unknown_opponent';
      return result;
    }
    const hasUnk = cards.some((c) => !c || /\?/.test(c) || /X/.test(c));
    if (hasUnk) {
      result.reasonIfSkipped = 'unknown_opponent';
      return result;
    }
    players.push({ hand: cards });
  }
  // Check player count against allowed maximum.
  const maxPlayers = opts?.maxPlayers ?? ctx.maxPlayers;
  if (typeof maxPlayers === 'number' && players.length > maxPlayers) {
    result.reasonIfSkipped = 'too_many_players';
    return result;
  }
  const board = ctx.board ?? [];
  // Dead cards: omitted in this phase; can be extended later.
  const dead: string[] = [];
  const exact = !!opts?.exact;
  // Choose iters for Monte Carlo; reuse preflop default if unspecified.
  const iters = opts?.iters ?? DEFAULT_ITERS_PREFLOP;
  const body = {
    players,
    board,
    dead,
    iters: exact ? undefined : iters,
    exact,
  };
  const signatureObj = { players, board, dead, exact, iters: body.iters ?? null };
  result.body = body;
  result.signature = stableHash(signatureObj);
  return result;
}
