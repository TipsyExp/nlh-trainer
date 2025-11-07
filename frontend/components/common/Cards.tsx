// frontend/components/common/Cards.tsx
import React from "react";
import clsx from "clsx";

type Suit = "h" | "d" | "c" | "s";

export type CardCode = string; // e.g., "Ah", "Kd", "3s"

/** Normalize a "Rs" code (rank+suit) into parts + presentation props. */
function normalizeCard(code: string) {
  const raw = (code || "").trim();
  if (raw.length < 2) {
    return null;
  }
  const rank = raw[0]!.toUpperCase();
  const s = raw.slice(1).toLowerCase();

  const suit: Suit | null =
    s.startsWith("h")
      ? "h"
      : s.startsWith("d")
      ? "d"
      : s.startsWith("c")
      ? "c"
      : s.startsWith("s")
      ? "s"
      : null;

  if (!suit) return null;

  const symbol =
    suit === "h" ? "♥" : suit === "d" ? "♦" : suit === "c" ? "♣" : "♠";
  const color = suit === "h" || suit === "d" ? "text-red-600" : "text-gray-900";
  const aria = `${rank} of ${suit === "h" ? "hearts" : suit === "d" ? "diamonds" : suit === "c" ? "clubs" : "spades"}`;

  return { rank, suit, symbol, color, aria };
}

type Size = "sm" | "md" | "lg";

const sizeMap: Record<Size, { padX: string; padY: string; text: string; gap: string; minW: string; minH: string }> = {
  sm: { padX: "px-1.5", padY: "py-0.5", text: "text-xs", gap: "gap-0.5", minW: "min-w-[28px]", minH: "min-h-[20px]" },
  md: { padX: "px-2",   padY: "py-1",   text: "text-sm", gap: "gap-1",   minW: "min-w-[34px]", minH: "min-h-[26px]" },
  lg: { padX: "px-2.5", padY: "py-1.5", text: "text-base", gap: "gap-1.5", minW: "min-w-[40px]", minH: "min-h-[32px]" },
};

export interface CardPillProps {
  code?: CardCode | null;
  size?: Size;
  className?: string;
  onClick?: () => void;
  title?: string;
}

/** Single card pill (e.g., "Ah"). Unknown/empty renders a neutral back. */
export function CardPill({
  code,
  size = "md",
  className,
  onClick,
  title,
}: CardPillProps) {
  const s = sizeMap[size];
  const parsed = code ? normalizeCard(code) : null;

  if (!parsed) {
    // Unknown card / placeholder
    return (
      <div
        aria-label="Unknown card"
        title={title || "Unknown"}
        onClick={onClick}
        className={clsx(
          "inline-flex items-center justify-center rounded-md border border-gray-300 bg-gray-100",
          "text-gray-500 shadow-sm",
          s.padX,
          s.padY,
          s.text,
          s.minW,
          s.minH,
          className
        )}
      >
        ??
      </div>
    );
  }

  const { rank, symbol, color, aria } = parsed;

  return (
    <div
      role="img"
      aria-label={aria}
      title={title || aria}
      onClick={onClick}
      className={clsx(
        "inline-flex items-center justify-center rounded-md border bg-white shadow-sm ring-1 ring-gray-200",
        s.padX,
        s.padY,
        s.text,
        s.minW,
        s.minH,
        className
      )}
    >
      <span className={clsx("font-semibold mr-0.5", color)}>{rank}</span>
      <span className={clsx("leading-none", color)}>{symbol}</span>
    </div>
  );
}

export interface CardsRowProps {
  cards?: Array<CardCode | null | undefined>;
  size?: Size;
  className?: string;
  gap?: string; // tailwind gap utility override
  compact?: boolean;
  /** If provided and cards array shorter than target, pad with unknowns to that length. */
  padTo?: number;
}

/** Row of cards with sensible spacing. Handles null/undefined gracefully. */
export function CardsRow({
  cards = [],
  size = "md",
  className,
  gap,
  compact = false,
  padTo,
}: CardsRowProps) {
  const s = sizeMap[size];
  const list = [...cards];
  if (padTo && padTo > list.length) {
    while (list.length < padTo) list.push(null);
  }

  return (
    <div
      className={clsx(
        "flex items-center",
        gap || s.gap,
        compact && "opacity-90",
        className
      )}
    >
      {list.map((c, i) => (
        <CardPill key={`${c || "unknown"}-${i}`} code={c || null} size={size} />
      ))}
    </div>
  );
}

/** Convenience: render a standard community board row. */
export function BoardRow({
  flop,
  turn,
  river,
  size = "md",
  className,
}: {
  flop?: Array<CardCode | null>;
  turn?: CardCode | null;
  river?: CardCode | null;
  size?: Size;
  className?: string;
}) {
  const f = flop ?? [];
  const t = turn ? [turn] : [];
  const r = river ? [river] : [];
  return (
    <div className={clsx("flex items-center gap-2", className)}>
      <CardsRow cards={f} size={size} padTo={3} />
      {t.length > 0 && <CardsRow cards={t} size={size} />}
      {r.length > 0 && <CardsRow cards={r} size={size} />}
    </div>
  );
}

export default CardsRow;
