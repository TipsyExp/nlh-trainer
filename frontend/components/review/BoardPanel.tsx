// frontend/components/review/BoardPanel.tsx
import React from "react";
import clsx from "clsx";

export interface BoardPanelProps {
  /** Full board array (e.g., ["Ah","Kd","3s","7h","2c"]). Optional. */
  board?: string[] | null;
  /** If provided, overrides the board-derived flop. */
  flop?: string[] | null;
  /** If provided, overrides the board-derived turn (1 card). */
  turn?: string[] | null;
  /** If provided, overrides the board-derived river (1 card). */
  river?: string[] | null;
  className?: string;
}

function normalizeCard(code: string) {
  // Ensure standardized formatting like "Ah", "Kd", lowercase suit
  const c = String(code).trim();
  if (!c) return c;
  const r = c[0]?.toUpperCase() ?? "";
  const s = c[1]?.toLowerCase() ?? "";
  return r + s;
}

function splitBoard(board?: string[] | null) {
  const b = Array.isArray(board) ? board.map(normalizeCard) : [];
  const flop = b.slice(0, 3);
  const turn = b.length >= 4 ? [b[3]] : [];
  const river = b.length >= 5 ? [b[4]] : [];
  return { flop, turn, river };
}

function CardPill({ code }: { code: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-md border border-gray-200",
        "bg-white px-2 py-1 text-xs font-medium shadow-sm",
        "tabular-nums text-gray-800"
      )}
      title={code}
    >
      {code}
    </span>
  );
}

function CardsRow({ cards }: { cards: string[] }) {
  if (!cards || cards.length === 0) return <span className="text-gray-400">—</span>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {cards.map((c, i) => (
        <CardPill key={`${c}-${i}`} code={normalizeCard(c)} />
      ))}
    </div>
  );
}

export default function BoardPanel({
  board,
  flop: flopOverride,
  turn: turnOverride,
  river: riverOverride,
  className,
}: BoardPanelProps) {
  const derived = splitBoard(board ?? undefined);
  const flop = flopOverride ?? derived.flop;
  const turn = turnOverride ?? derived.turn;
  const river = riverOverride ?? derived.river;

  const hasAny =
    (flop && flop.length > 0) ||
    (turn && turn.length > 0) ||
    (river && river.length > 0);

  return (
    <div
      className={clsx(
        "rounded-2xl border border-gray-200 bg-white/60 backdrop-blur shadow-sm",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div className="text-sm font-medium text-gray-900">Board</div>
        <div className="text-xs text-gray-500">Flop / Turn / River</div>
      </div>

      {!hasAny ? (
        <div className="px-4 py-4 text-sm text-gray-600">No board info.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 px-4 py-4 md:grid-cols-3">
          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-gray-500">
              Flop
            </div>
            <CardsRow cards={flop ?? []} />
          </div>

          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-gray-500">
              Turn
            </div>
            <CardsRow cards={turn ?? []} />
          </div>

          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-gray-500">
              River
            </div>
            <CardsRow cards={river ?? []} />
          </div>
        </div>
      )}
    </div>
  );
}
