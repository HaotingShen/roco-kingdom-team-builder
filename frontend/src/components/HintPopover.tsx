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
  /**
   * Override color classes for the trigger button. Use this when the button
   * sits on a tinted background (e.g. blue/indigo cards) and the default
   * white/zinc style looks out of place.
   */
  buttonClassName?: string;
  /** Character shown inside the button. Defaults to "?" — pass "i" for informational tips. */
  label?: string;
  /**
   * Horizontal alignment of the popover relative to the trigger button.
   * - "center" (default) — centered on the button; can overflow on left-edge buttons
   * - "left" — left edge of popover aligns with left edge of button; safe near left borders
   * - "right" — right edge of popover aligns with right edge of button; safe near right borders
   */
  align?: "center" | "left" | "right";
}

export default function HintPopover({
  text,
  ariaLabel = "Help",
  className = "",
  buttonClassName,
  label = "?",
  align = "center",
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

  // Close on Escape — standard expected behaviour for any popover.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <span ref={wrapperRef} className={`relative inline-flex items-center flex-none ${className}`}>
      <button
        type="button"
        onClick={(e) => {
          // Stop the wrapper's mousedown listener from immediately re-closing.
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-label={ariaLabel}
        aria-expanded={open}
        className={buttonClassName ?? "shrink-0 inline-flex items-center justify-center w-[18px] h-[18px] rounded-full border border-zinc-300 bg-white text-zinc-500 text-xs font-bold leading-none cursor-pointer hover:bg-zinc-50 hover:border-zinc-400 hover:text-zinc-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"}
      >
        {label}
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute z-20 top-[calc(100%+4px)] w-52 max-w-[75vw] px-3 py-2 rounded-lg border border-zinc-200 bg-white shadow-lg text-xs text-zinc-700 leading-relaxed whitespace-normal ${
            align === "left" ? "left-0" : align === "right" ? "right-0" : "left-1/2 -translate-x-1/2"
          }`}
        >
          {text}
        </span>
      )}
    </span>
  );
}
