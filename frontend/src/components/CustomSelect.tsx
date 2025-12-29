import { useEffect, useLayoutEffect, useRef, useState, useId } from "react";

export type CustomSelectOption = {
  value: number;
  label: string;
  rightLabel?: string;
  disabled?: boolean;
  leftIconUrl?: string | null;
  title?: string;
  /** Show red exclamation mark on hover when disabled (default: false) */
  showDisabledIndicator?: boolean;
};

type Props = {
  value: number | null | undefined;
  options: CustomSelectOption[];
  onChange: (v: number) => void;
  placeholder?: string;
  ariaLabel?: string;

  /** Optional styling hooks */
  buttonClassName?: string;     // e.g. "w-full" or "min-w-[200px]"
  containerClassName?: string;  // e.g. "flex-1 min-w-0"
  menuClassName?: string;       // to tweak menu if needed

  /** disable the whole control (no open/click) */
  disabled?: boolean;
};

export default function CustomSelect({
  value,
  options,
  onChange,
  placeholder = "—",
  ariaLabel,
  buttonClassName = "w-full",
  containerClassName = "",
  menuClassName = "",
  disabled = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<"bottom" | "top">("bottom");
  const [maxH, setMaxH] = useState<number>(288); // ~max-h-72
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  function recomputeFrom(btn: HTMLButtonElement) {
    const r = btn.getBoundingClientRect();
    const GAP = 8;
    const vh = window.visualViewport?.height ?? window.innerHeight;

    // Find nearest scrolling parent container
    let scrollParent: HTMLElement | null = null;
    let parent = btn.parentElement;
    while (parent && parent !== document.body) {
      const overflow = window.getComputedStyle(parent).overflowY;
      if (overflow === 'auto' || overflow === 'scroll') {
        scrollParent = parent;
        break;
      }
      parent = parent.parentElement;
    }

    let spaceBelow: number;
    let spaceAbove: number;

    if (scrollParent) {
      // Calculate space within scrolling container's visible area
      const parentRect = scrollParent.getBoundingClientRect();

      // Space below = distance from button bottom to parent's visible bottom edge
      const parentVisibleBottom = Math.min(parentRect.bottom, vh);
      spaceBelow = parentVisibleBottom - r.bottom - GAP;

      // Space above = distance from button top to parent's visible top edge
      const parentVisibleTop = Math.max(parentRect.top, 0);
      spaceAbove = r.top - parentVisibleTop - GAP;

      // Ensure we don't have negative space
      spaceBelow = Math.max(0, spaceBelow);
      spaceAbove = Math.max(0, spaceAbove);
    } else {
      // Fallback to viewport-based calculation
      spaceBelow = vh - r.bottom - GAP;
      spaceAbove = r.top - GAP;
    }

    // Decide whether to flip upward
    const flipUp = spaceBelow < 240 && spaceAbove > spaceBelow;
    setPlacement(flipUp ? "top" : "bottom");

    // Calculate usable height with more conservative minimum
    const usable = Math.max(120, Math.floor(flipUp ? spaceAbove : spaceBelow));
    setMaxH(usable);
  }

  // Close on outside click
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      const n = e.target as Node;
      if (popRef.current && !popRef.current.contains(n) && btnRef.current && !btnRef.current.contains(n)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Keep placement accurate while open (no flicker)
  useLayoutEffect(() => {
    if (!open) return;
    const handler = () => { if (btnRef.current) recomputeFrom(btnRef.current); };
    handler();
    window.addEventListener("resize", handler);
    window.addEventListener("scroll", handler, true);
    window.visualViewport?.addEventListener("resize", handler);
    return () => {
      window.removeEventListener("resize", handler);
      window.removeEventListener("scroll", handler, true);
      window.visualViewport?.removeEventListener("resize", handler);
    };
  }, [open]);

  const current = options.find(o => o.value === value);
  const display = current ? current.label : placeholder;
  const displayIcon = current?.leftIconUrl || null;

  // Compute BEFORE opening to avoid initial down-then-up blink
  const toggleOpen = () => {
    if (disabled) return;
    if (open) { setOpen(false); return; }
    if (btnRef.current) recomputeFrom(btnRef.current);
    setOpen(true);
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLButtonElement> = (e) => {
    if (disabled) return;
    if (!open && (e.key === "Enter" || e.key === " " || e.key === "ArrowDown")) {
      e.preventDefault();
      if (btnRef.current) recomputeFrom(btnRef.current);
      setOpen(true);
      return;
    }
    if (open && e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className={`relative ${containerClassName}`}>
      <button
        ref={btnRef}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-disabled={disabled || undefined}
        disabled={disabled}
        onClick={toggleOpen}
        onKeyDown={onKeyDown}
        className={`h-9 border rounded px-3 flex items-center justify-between ${disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer"} ${buttonClassName}`}
      >
        <span className="truncate flex items-center gap-1">
          {displayIcon ? (
            <img
              src={displayIcon}
              alt=""
              width={22}
              height={22}
              className="inline-block"
              onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
            />
          ) : null}
          <span className="truncate">{display}</span>
        </span>
        <svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true">
          <path d="M5 7l5 6 5-6" fill="currentColor" />
        </svg>
      </button>

      {open && (
        <div
          ref={popRef}
          id={listboxId}
          role="listbox"
          className={`absolute z-50 w-full border-2 border-zinc-300 rounded-lg bg-white shadow-xl overflow-auto left-0
            ${placement === "bottom" ? "top-full mt-1" : "bottom-full mb-1"} ${menuClassName}`}
          style={{ maxHeight: maxH }}
          onWheel={(e) => e.stopPropagation()}
          onTouchMove={(e) => e.stopPropagation()}
        >
          {options.map(opt => {
            const selected = opt.value === value;
            const isDisabled = !!opt.disabled || disabled;
            return (
              <div
                key={opt.value}
                role="option"
                aria-selected={selected}
                aria-disabled={isDisabled || undefined}
                title={opt.title}
                onClick={() => {
                  if (isDisabled) return;
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`px-3 py-2 flex items-center gap-2 cursor-pointer hover:bg-zinc-50 group relative
                  ${selected ? "bg-zinc-100" : ""} ${isDisabled ? "opacity-40 cursor-not-allowed hover:bg-transparent" : ""}`}
              >
                {opt.leftIconUrl ? (
                  <img
                    src={opt.leftIconUrl}
                    alt=""
                    width={22}
                    height={22}
                    onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
                  />
                ) : null}
                <span className="truncate">{opt.label}</span>
                {opt.rightLabel ? (
                  <span className="ml-auto text-right text-xs text-zinc-600">{opt.rightLabel}</span>
                ) : null}
                {isDisabled && opt.showDisabledIndicator && (
                  <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity inline-flex items-center justify-center w-4 h-4 rounded-full bg-red-500 text-white text-xs font-bold shrink-0">
                    !
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}