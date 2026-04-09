import { useEffect, useRef, useState } from "react";

/**
 * Small reusable "?" button that opens a short hint popover next to itself.
 *
 * Use this for inline contextual help anywhere a label would benefit from a
 * one- or two-sentence explanation that the user can pull up on demand —
 * e.g. clarifying what the rows in MoveCoveragePanel mean.
 *
 * Interaction model:
 *   - Click / tap the "?" to toggle the popover (works on mobile)
 *   - Click outside (anywhere not in the wrapper) to close
 *   - aria-expanded reflects state for screen readers
 *
 * Implementation notes:
 *   - No external dependencies, no portal — pure absolute positioning
 *     relative to the wrapping span
 *   - Popover anchors at `top-full left-0` and is constrained to a sensible
 *     max width with text wrapping; suitable for short hints (1–2 sentences)
 *   - z-20 keeps it above the surrounding card content but doesn't fight
 *     with modals (which use higher z indices)
 */

interface HintPopoverProps {
  /** The hint text shown in the popover when open. */
  text: string;
  /**
   * aria-label for the trigger button. Defaults to "Help" — pass an
   * already-localised string from your i18n layer if you want it translated.
   */
  ariaLabel?: string;
  /** Optional extra classes for the wrapper span. */
  className?: string;
}

export default function HintPopover({
  text,
  ariaLabel = "Help",
  className = "",
}: HintPopoverProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLSpanElement>(null);

  // Close on click outside the wrapper. Only attach the listener while open
  // so we're not running mousedown handlers all the time.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <span ref={wrapperRef} className={`relative inline-flex items-center ${className}`}>
      <button
        type="button"
        onClick={(e) => {
          // Stop the wrapper's mousedown listener from immediately re-closing.
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-label={ariaLabel}
        aria-expanded={open}
        className="inline-flex items-center justify-center w-4 h-4 sm:w-[18px] sm:h-[18px] rounded-full border border-zinc-300 bg-white text-zinc-500 text-[10px] sm:text-xs font-bold leading-none cursor-pointer hover:bg-zinc-50 hover:border-zinc-400 hover:text-zinc-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute z-20 left-0 top-[calc(100%+4px)] w-64 max-w-[80vw] px-3 py-2 rounded-lg border border-zinc-200 bg-white shadow-lg text-xs text-zinc-700 leading-relaxed whitespace-normal"
        >
          {text}
        </span>
      )}
    </span>
  );
}
