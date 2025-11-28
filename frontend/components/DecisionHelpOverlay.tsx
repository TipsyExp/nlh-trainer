// frontend/components/DecisionHelpOverlay.tsx
// Presentational overlay for hand guidance (unified advice payload).
//
// This component renders a fixed panel on the right side of the screen (or
// bottom on small screens) and displays coach advice (charts / solver) plus
// optional equity annotations for the current decision. All network logic is
// handled by hooks; this component only consumes the normalised state
// returned by `useDecisionOverlay` and renders it.

import React from "react";
import type { DecisionContext } from "../types/decision";
import type { AdvicePayloadV1 } from "../types/advice";
import { StrategyBar } from "./common/StrategyBar";
import { StatusChip } from "./StatusChip";
import { HeroEquityBar } from "./HeroEquityBar";

export interface DecisionHelpOverlayProps {
  /** Optional decision context (used for supplemental UI like stacks). */
  decision?: DecisionContext | null;
  /** Normalised advice state from useDecisionOverlay. */
  advice: {
    data: AdvicePayloadV1 | null;
    loading: boolean;
    status: "ok" | "loading" | "disabled" | "not_found" | "unavailable";
    error?: string;
  };
}

export function DecisionHelpOverlay({
  decision,
  advice,
}: DecisionHelpOverlayProps) {
  const payload = advice.data ?? null;

  const recommendation = payload?.recommendation ?? null;
  const equity = payload?.equity ?? null;
  const thresholds = payload?.thresholds ?? null;
  const ctx = payload?.context ?? null;
  const meta = payload?.meta ?? null;

  // ---- Source label normalisation ----------------------------------------

  const rawSource = (meta?.source || "").toString().toLowerCase();
  let sourceLabel: string;
  if (!payload) {
    sourceLabel = "—";
  } else if (!rawSource) {
    sourceLabel = "Coach";
  } else if (rawSource.includes("solver") || rawSource.includes("texas")) {
    sourceLabel = "Solver";
  } else if (rawSource.includes("equity")) {
    sourceLabel = "Equity";
  } else if (rawSource.includes("chart") || rawSource.includes("preflop")) {
    sourceLabel = "Chart";
  } else {
    // Fallback to the raw backend label if we don't recognise it.
    sourceLabel = meta!.source!;
  }

  // ---- Strategy parts ----------------------------------------------------

  // Strategy parts: prefer backend strategy_bar; fall back to action_mix
  const strategyParts =
    recommendation &&
    Array.isArray(recommendation.strategy_bar) &&
    recommendation.strategy_bar.length > 0
      ? recommendation.strategy_bar
          .map((p) => ({
            action: String(p.action),
            weight: typeof p.weight === "number" ? p.weight : Number(p.weight),
          }))
          .filter((p) => Number.isFinite(p.weight) && p.weight > 0)
      : recommendation && recommendation.action_mix
      ? Object.entries(recommendation.action_mix)
          .map(([action, weight]) => ({
            action,
            weight:
              typeof weight === "number" ? weight : Number(weight ?? 0),
          }))
          .filter((p) => Number.isFinite(p.weight) && p.weight > 0)
      : [];

  // Shape for common/StrategyBar
  const strategyEntries =
    strategyParts.length > 0
      ? strategyParts.map((p) => ({
          key: p.action,
          p: p.weight,
          label: p.action,
        }))
      : [];

  // Primary action: prefer bucket; fall back to primary_action if present.
  const primaryAction =
    recommendation?.bucket ?? recommendation?.primary_action ?? null;

  // ---- Equity / thresholds -----------------------------------------------

  const heroEquity =
    typeof equity?.hero === "number" ? equity.hero : null;

  const potOdds =
    typeof thresholds?.pot_odds === "number" ? thresholds.pot_odds : null;

  const minEqToCall =
    typeof thresholds?.min_equity_to_call === "number"
      ? thresholds.min_equity_to_call
      : null;

  const equityComment =
    (equity?.comment ?? thresholds?.ev_hint ?? payload?.rationale) || null;

  // ---- Context / stacks / header fields ----------------------------------

  const streetLabel =
    (ctx?.street ?? meta?.street ?? decision?.street ?? "unknown") || "unknown";

  const heroPosLabel = ctx?.hero_position ?? "unknown";

  const toCall =
    typeof ctx?.to_call === "number"
      ? ctx.to_call
      : decision?.toCall ?? 0;

  const potSize =
    typeof ctx?.pot_size === "number"
      ? ctx.pot_size
      : decision?.pot ?? 0;

  const effectiveStackChips =
    typeof ctx?.stack_effective === "number"
      ? ctx.stack_effective
      : decision?.effectiveStack ?? null;

  return (
    <div
      role="region"
      aria-label="Guidance"
      className="fixed z-40 right-4 top-4 md:right-4 md:top-4 max-w-[90vw] w-80 md:w-96"
    >
      <div className="bg-white shadow-lg rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Guidance</h2>
          {/* Status badge summarises the current advice state */}
          <StatusChip status={advice.status} />
        </div>

        {/* Advice section */}
        {advice.status === "loading" && (
          <div className="space-y-2">
            <div className="h-4 w-32 bg-gray-100 animate-pulse rounded" />
            <div className="h-3 w-24 bg-gray-100 animate-pulse rounded" />
          </div>
        )}

        {advice.status === "disabled" && (
          <div className="text-sm text-gray-600">
            Advice disabled or not configured.
          </div>
        )}

        {advice.status === "not_found" && (
          <div className="text-sm text-gray-600">
            Advice route not available.
          </div>
        )}

        {advice.status === "unavailable" && (
          <div className="text-sm text-gray-600">
            Advice unavailable.
          </div>
        )}

        {advice.status === "ok" && payload && (
          <div className="space-y-3 text-sm">
            {/* Source badge and header line */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Source:</span>
              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700">
                {sourceLabel}
              </span>
            </div>

            {(ctx || decision) && (
              <div className="text-xs text-gray-500 flex flex-wrap gap-x-2 gap-y-1">
                <span className="uppercase">
                  {String(streetLabel)} · {String(heroPosLabel)}
                </span>
                <span>To call: {toCall}</span>
                <span>Pot: {potSize}</span>
                {effectiveStackChips != null && (
                  <span>Eff. stack: {effectiveStackChips}</span>
                )}
              </div>
            )}

            <div>
              <span className="text-gray-500 mr-1">Recommended:</span>
              <span className="font-medium capitalize">
                {primaryAction
                  ? primaryAction.replace(/_/g, " ")
                  : "—"}
              </span>
            </div>

            {/* Strategy bar if we have a mix */}
            {strategyEntries.length > 0 && (
              <div className="space-y-1">
                <StrategyBar
                  data={strategyEntries}
                  precision={0}
                  showLegend={true}
                  size="sm"
                  ariaLabel="Recommended action mix"
                />
              </div>
            )}

            {/* Optional comment / rationale */}
            {equityComment && (
              <div className="text-xs text-gray-500">{equityComment}</div>
            )}
          </div>
        )}

        {/* Equity / thresholds block */}
        {payload && (
          <div className="mt-3 border-t pt-3 space-y-2">
            {advice.status === "loading" && (
              <div className="space-y-2">
                <div className="h-4 w-32 bg-gray-100 animate-pulse rounded" />
                <div className="h-3 w-24 bg-gray-100 animate-pulse rounded" />
              </div>
            )}

            {advice.status === "ok" && (
              <div className="space-y-2 text-sm">
                {/* Hero equity */}
                {heroEquity !== null && (
                  <>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">
                        Equity vs villain:
                      </span>
                      <span className="font-medium">
                        {(heroEquity * 100).toFixed(1)}%
                      </span>
                    </div>
                    <HeroEquityBar equity={heroEquity} />
                  </>
                )}

                {/* Pot odds / min equity to call */}
                {(potOdds !== null || minEqToCall !== null) && (
                  <div className="flex flex-col gap-1 text-xs text-gray-500">
                    {potOdds !== null && (
                      <span>
                        Pot odds: {(potOdds * 100).toFixed(1)}%
                      </span>
                    )}
                    {minEqToCall !== null && (
                      <span>
                        Min equity to call:{" "}
                        {(minEqToCall * 100).toFixed(1)}%
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default DecisionHelpOverlay;
