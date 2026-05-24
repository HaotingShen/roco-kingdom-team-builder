import { useState, useCallback, useRef, useEffect, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "@/i18n";
import { useGameTerms, type ParsedGameTerm } from "@/hooks/useGameTerms";

// ---- Types ----

interface TextSeg { type: "text"; content: string }
interface TermSeg { type: "term"; content: string; term: ParsedGameTerm }
type Segment = TextSeg | TermSeg;

// ---- Parser ----

function splitByTerm(text: string, term: ParsedGameTerm, isZh: boolean): Segment[] {
  const result: Segment[] = [];

  if (isZh) {
    let remaining = text;
    while (remaining.length > 0) {
      const idx = remaining.indexOf(term.matchName);
      if (idx === -1) { result.push({ type: "text", content: remaining }); break; }
      if (idx > 0) result.push({ type: "text", content: remaining.slice(0, idx) });
      result.push({ type: "term", content: term.matchName, term });
      remaining = remaining.slice(idx + term.matchName.length);
    }
  } else {
    const escaped = term.matchName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // Case-sensitive: "Move Power" must match exactly, not "move power" / "Move power".
    // Negative lookahead suppresses type-reference contexts like "Poison-type Status moves",
    // where the term name is being used as a Pokémon-style elemental type, not the status.
    const regex = new RegExp(`\\b(${escaped})\\b(?!-[Tt]ype)`, "g");
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) result.push({ type: "text", content: text.slice(lastIndex, match.index) });
      result.push({ type: "term", content: match[1] ?? match[0], term });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < text.length) result.push({ type: "text", content: text.slice(lastIndex) });
    if (result.length === 0) result.push({ type: "text", content: text });
  }
  return result;
}

function parseSegments(text: string, terms: ParsedGameTerm[], isZh: boolean): Segment[] {
  if (!text || terms.length === 0) return [{ type: "text", content: text }];
  let segments: Segment[] = [{ type: "text", content: text }];
  for (const term of terms) {
    const next: Segment[] = [];
    for (const seg of segments) {
      if (seg.type !== "text") { next.push(seg); continue; }
      next.push(...splitByTerm(seg.content, term, isZh));
    }
    segments = next;
  }
  return segments;
}

// ---- TermTooltip ----

// For tooltips near the right screen edge, position:absolute expands
// document.scrollWidth which shifts the sticky sidebar. position:fixed
// elements are never part of document flow so they never affect scrollWidth.
// useLayoutEffect fires before paint, so the user never sees the bubble at
// its initial off-screen position (top:-9999) — only the final clamped position.
// Visual output is pixel-identical to the original for non-edge cases.

interface TooltipPos { left: number; top: number; caretLeft: number; ready: boolean }
const HIDDEN_POS: TooltipPos = { left: 0, top: -9999, caretLeft: 8, ready: false };

function TermTooltip({ seg }: { seg: TermSeg }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState<TooltipPos>(HIDDEN_POS);
  const spanRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!show) return;
    const close = () => setShow(false);
    const handleMouseDown = (e: MouseEvent) => {
      if (spanRef.current && !spanRef.current.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", handleMouseDown, { capture: true });
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown, { capture: true });
      window.removeEventListener("scroll", close, true);
    };
  }, [show]);

  // Compute fixed pixel coordinates before paint.
  // Default position mirrors the original absolute tooltip exactly:
  //   vertical: trigger.top - tipHeight - 8px  (matches bottom-full + mb-2)
  //   horizontal: centered on trigger            (matches left-1/2 -translate-x-1/2)
  // Then clamp left so the bubble never exits the viewport horizontally.
  useLayoutEffect(() => {
    if (!show || !spanRef.current || !tooltipRef.current) {
      setPos(HIDDEN_POS);
      return;
    }
    const trigger = spanRef.current.getBoundingClientRect();
    const tip = tooltipRef.current.getBoundingClientRect();
    const vw = document.documentElement.clientWidth; // excludes scrollbar
    const pad = 8;

    const centerX = trigger.left + trigger.width / 2;
    let left = centerX - tip.width / 2;
    // Clamp: don't let either edge leave the viewport
    if (left + tip.width > vw - pad) left = vw - pad - tip.width;
    if (left < pad) left = pad;

    const top = trigger.top - tip.height - 8; // 8px = mb-2 gap
    // Keep the caret pointing at the trigger word even after horizontal shift
    const caretLeft = Math.max(6, Math.min(tip.width - 6, centerX - left));

    setPos({ left, top, caretLeft, ready: true });
  }, [show]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setShow((v) => !v);
  }, []);

  return (
    <span
      ref={spanRef}
      className="relative inline cursor-help underline decoration-dotted decoration-zinc-400 underline-offset-2"
      onPointerEnter={(e) => { if (e.pointerType === "mouse") setShow(true); }}
      onPointerLeave={(e) => { if (e.pointerType === "mouse") setShow(false); }}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setShow((v) => !v); }}
      aria-label={`${seg.term.key}: ${seg.term.fullDescription}`}
    >
      {seg.content}
      {show && createPortal(
        <span
          ref={tooltipRef}
          className="fixed w-max max-w-[240px] sm:max-w-[300px] px-2.5 py-1.5 rounded bg-zinc-800 text-white text-xs leading-snug whitespace-normal break-words z-30 pointer-events-none shadow-lg"
          style={{ left: pos.left, top: pos.top, visibility: pos.ready ? "visible" : "hidden" }}
        >
          {seg.term.tooltipText}
          <span
            className="absolute top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-800"
            style={{ left: pos.caretLeft }}
          />
        </span>,
        document.body
      )}
    </span>
  );
}

// ---- RichDescription ----

export default function RichDescription({ text, className }: { text: string; className?: string }) {
  const { lang } = useI18n();
  const terms = useGameTerms(lang);
  if (!text) return null;
  const segments = parseSegments(text, terms, lang === "zh");
  return (
    <span className={className}>
      {segments.map((seg, i) =>
        seg.type === "text"
          ? <span key={i}>{seg.content}</span>
          : <TermTooltip key={`${seg.term.key}-${i}`} seg={seg} />
      )}
    </span>
  );
}
