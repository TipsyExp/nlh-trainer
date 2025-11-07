// frontend/components/review/ActionStepper.tsx
import React from "react";
import clsx from "clsx";

export interface ActionStepperProps {
  /** Zero-based index of the current action */
  index: number;
  /** Total number of actions */
  total: number;
  /** Called with the new index when stepping */
  onStep: (nextIndex: number) => void;
  /** Wrap around when hitting ends (default: false) */
  loop?: boolean;
  /** Bind ←/→ (and Home/End) keyboard handlers (default: true) */
  hotkeys?: boolean;
  /** Compact style (smaller paddings) */
  compact?: boolean;
  className?: string;
}

function isTextInput(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  const editable = el.getAttribute("contenteditable");
  return (
    tag === "input" ||
    tag === "textarea" ||
    editable === "" ||
    editable === "true"
  );
}

export default function ActionStepper({
  index,
  total,
  onStep,
  loop = false,
  hotkeys = true,
  compact = false,
  className,
}: ActionStepperProps) {
  const canPrev = total > 0 && (loop || index > 0);
  const canNext = total > 0 && (loop || index < total - 1);

  const stepPrev = React.useCallback(() => {
    if (!canPrev) return;
    if (index === 0 && loop) {
      onStep(Math.max(0, total - 1));
    } else {
      onStep(Math.max(0, index - 1));
    }
  }, [canPrev, index, loop, onStep, total]);

  const stepNext = React.useCallback(() => {
    if (!canNext) return;
    if (index === total - 1 && loop) {
      onStep(0);
    } else {
      onStep(Math.min(total - 1, index + 1));
    }
  }, [canNext, index, loop, onStep, total]);

  const stepFirst = React.useCallback(() => {
    if (total > 0) onStep(0);
  }, [onStep, total]);

  const stepLast = React.useCallback(() => {
    if (total > 0) onStep(total - 1);
  }, [onStep, total]);

  // Keyboard handlers: ← / →, Home / End
  React.useEffect(() => {
    if (!hotkeys) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.altKey || e.metaKey || e.ctrlKey) return; // avoid clashing with browser/system shortcuts
      if (isTextInput(e.target)) return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        stepPrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        stepNext();
      } else if (e.key === "Home") {
        e.preventDefault();
        stepFirst();
      } else if (e.key === "End") {
        e.preventDefault();
        stepLast();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hotkeys, stepPrev, stepNext, stepFirst, stepLast]);

  return (
    <div
      className={clsx(
        "flex items-center justify-between rounded-2xl border border-gray-200 bg-white/60 px-3 py-2 shadow-sm backdrop-blur",
        className
      )}
    >
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={stepFirst}
          disabled={total === 0 || (!loop && index === 0)}
          className={clsx(
            baseBtnClass(compact),
            "rounded-l-xl",
            btnDisabledClass(total === 0 || (!loop && index === 0))
          )}
          aria-label="First action (Home)"
          title="First (Home)"
        >
          «
        </button>
        <button
          type="button"
          onClick={stepPrev}
          disabled={!canPrev}
          className={clsx(
            baseBtnClass(compact),
            btnDisabledClass(!canPrev)
          )}
          aria-label="Previous action (←)"
          title="Prev (←)"
        >
          ‹
        </button>
      </div>

      <div className="mx-2 select-none text-sm font-medium text-gray-800 tabular-nums">
        {total > 0 ? `Action ${index + 1} / ${total}` : "No actions"}
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={stepNext}
          disabled={!canNext}
          className={clsx(
            baseBtnClass(compact),
            btnDisabledClass(!canNext)
          )}
          aria-label="Next action (→)"
          title="Next (→)"
        >
          ›
        </button>
        <button
          type="button"
          onClick={stepLast}
          disabled={total === 0 || (!loop && index === total - 1)}
          className={clsx(
            baseBtnClass(compact),
            "rounded-r-xl",
            btnDisabledClass(total === 0 || (!loop && index === total - 1))
          )}
          aria-label="Last action (End)"
          title="Last (End)"
        >
          »
        </button>
      </div>
    </div>
  );
}

function baseBtnClass(compact: boolean) {
  return clsx(
    "px-2 text-sm font-semibold text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50 active:bg-gray-100",
    "disabled:cursor-not-allowed disabled:opacity-40",
    compact ? "h-8" : "h-9"
  );
}

function btnDisabledClass(disabled: boolean) {
  return disabled ? "bg-white" : "bg-white";
}
