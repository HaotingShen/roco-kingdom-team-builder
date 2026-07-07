import { Link } from "react-router-dom";
import { Fragment, useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useI18n, pickName, pickFormName, type Lang } from "@/i18n";
import { monsterImageFallbackChain, typeIconUrl, monsterPlaceholder } from "@/lib/images";
import { buildDexForwardQuery } from "@/lib/dexNavigation";
import { useLocalizedPath } from "@/lib/locale";
import type { EvolutionTreeData, EvolutionStageMonster } from "@/types";

interface EvolutionTreeProps {
  treeData: EvolutionTreeData;
  currentMonsterId: number;
  fromTab: string;
  fromBuilder: boolean;
  fromAnalyze?: boolean;
  analyzeSlot?: string;
  fromMatchup?: boolean;
  back?: string;
}

export default function EvolutionTree({
  treeData,
  currentMonsterId,
  fromTab,
  fromBuilder,
  fromAnalyze = false,
  analyzeSlot,
  fromMatchup = false,
  back,
}: EvolutionTreeProps) {
  const { lang } = useI18n();
  const forwardQuery = buildDexForwardQuery({
    backRaw: back,
    fromTab,
    fromBuilder,
    fromAnalyze,
    analyzeSlot,
    fromMatchup,
  });

  if (!treeData || !treeData.stages || treeData.stages.length <= 1) {
    return null;
  }

  // Compute uniform evolution level per stage.
  // If all non-leader monsters at a stage share the same level, show it on the arrow.
  // Otherwise null — fall back to showing level on individual cards.
  const stageLevels: (number | null)[] = treeData.stages.map(stage => {
    const nonLeaders = stage.monsters.filter(m => !m.is_leader_form);
    const levels = nonLeaders
      .map(m => m.evolution_level)
      .filter((l): l is number => l != null);
    if (levels.length === 0) return null;
    return levels.every(l => l === levels[0]) ? levels[0]! : null;
  });

  return (
    <div className="overflow-x-auto py-4 px-1">
      {/* w-fit + mx-auto: centers when content fits, left-aligns when overflowing (no left-clip) */}
      <div className="flex items-center gap-2 sm:gap-3 w-fit mx-auto">
        {treeData.stages.map((stage, stageIndex) => (
          <Fragment key={stage.depth}>
            {/* Stage Column */}
            <div className="flex flex-col gap-1.5 sm:gap-2 shrink-0">
              {stage.monsters.map(monster => {
                // Show level on the card only when the stage level is non-uniform (null)
                const levelOnCard =
                  stageLevels[stageIndex] === null &&
                  monster.evolution_level != null &&
                  !monster.is_leader_form
                    ? monster.evolution_level
                    : null;
                const conditionOnCard =
                  monster.evolution_condition && !monster.is_leader_form
                    ? monster.evolution_condition
                    : null;

                return (
                  <MonsterEvolutionCard
                    key={monster.id}
                    monster={monster}
                    isCurrent={monster.id === currentMonsterId}
                    forwardQuery={forwardQuery}
                    lang={lang}
                    levelOnCard={levelOnCard}
                    conditionOnCard={conditionOnCard}
                  />
                );
              })}
            </div>

            {/* Arrow to next stage — carries uniform level badge if applicable */}
            {stageIndex < treeData.stages.length - 1 && (
              <EvolutionArrow
                isLeaderTransition={treeData.stages[stageIndex + 1]?.is_leader_stage}
                uniformLevel={stageLevels[stageIndex + 1]}
              />
            )}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function EvolutionArrow({
  isLeaderTransition,
  uniformLevel,
}: {
  isLeaderTransition?: boolean;
  uniformLevel?: number | null;
}) {
  // Leader icon for transitions TO leader forms — no level badge
  if (isLeaderTransition) {
    return (
      <div className="flex flex-col items-center justify-center shrink-0 px-1 sm:px-2">
        <img
          src={typeIconUrl("leader", 30)!}
          alt="Evolves to Leader"
          className="w-6 h-6 sm:w-7 sm:h-7 drop-shadow-md"
        />
      </div>
    );
  }

  // Styled evolution arrow with optional uniform level text
  return (
    <div className="flex flex-col items-center justify-center shrink-0 gap-0.5 px-1 sm:px-2">
      {uniformLevel != null && (
        <span className="text-[10px] sm:text-[11px] font-bold uppercase tracking-wide text-zinc-700 leading-none">
          Lv.{uniformLevel}
        </span>
      )}
      <svg
        className="w-6 h-6 sm:w-8 sm:h-8 opacity-80"
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="arrowGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#71717a" stopOpacity="0.5" />
            <stop offset="50%" stopColor="#52525b" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#27272a" stopOpacity="1" />
          </linearGradient>
        </defs>
        <path
          d="M 6 12 L 12 16 L 6 20"
          stroke="url(#arrowGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M 13 12 L 19 16 L 13 20"
          stroke="url(#arrowGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M 20 12 L 26 16 L 20 20"
          stroke="url(#arrowGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </div>
  );
}

// Pill that detects real DOM truncation and shows a fixed-position tooltip on
// hover (desktop) or tap (mobile). The portal escapes overflow-x-auto clipping.
function ConditionPill({ text }: { text: string }) {
  const pillRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [isTruncated, setIsTruncated] = useState(false);
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, above: true, arrowOffset: 0 });
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track whether the last interaction was touch — used to suppress synthesized
  // mouseleave events that fire after a tap and would immediately hide the tooltip.
  const lastPointerType = useRef<string>("");
  // Guards the one-shot overflow correction so we don't loop after adjusting.
  const hasAdjusted = useRef(false);

  // Re-check truncation whenever layout changes (resize, font load, etc.)
  useEffect(() => {
    const el = pillRef.current;
    if (!el) return;
    const check = () => setIsTruncated(el.scrollWidth > el.clientWidth);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text]);

  const calcPos = useCallback(() => {
    const el = pillRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const spaceAbove = rect.top;
    const above = spaceAbove >= 44;     // 40px tooltip height + 4px gap
    // Set tooltip centered at pill with no pre-clamping. useLayoutEffect below
    // will measure the actual rendered width and apply the minimal correction.
    setPos({
      top: above ? rect.top - 6 : rect.bottom + 6,
      left: centerX,
      above,
      arrowOffset: 0,
    });
  }, []);

  // After the tooltip renders, measure its real right/left edges and shift only
  // as much as needed. Runs before browser paint so there's no visible flash.
  // hasAdjusted prevents looping after the state update triggers a re-render.
  useLayoutEffect(() => {
    if (!visible || !tooltipRef.current || hasAdjusted.current) return;
    const rect = tooltipRef.current.getBoundingClientRect();
    const margin = 4;
    let shift = 0;
    if (rect.right > window.innerWidth - margin) {
      shift = rect.right - (window.innerWidth - margin);
    } else if (rect.left < margin) {
      shift = -(margin - rect.left);  // negative = shift right
    }
    // Always mark adjusted — even when no shift is needed — so subsequent
    // re-renders while the tooltip is visible don't re-run the measurement.
    hasAdjusted.current = true;
    if (shift !== 0) {
      setPos(prev => ({
        ...prev,
        left: prev.left - shift,
        // Arrow moves opposite to the tooltip shift so it stays over the pill.
        // Clamp to stay within rounded tooltip edges (~12px inset on each side).
        arrowOffset: Math.min(Math.max(shift, -88), 88),
      }));
    }
  });

  const open = useCallback(() => {
    hasAdjusted.current = false;
    if (hideTimer.current) clearTimeout(hideTimer.current);
    calcPos();
    setVisible(true);
  }, [calcPos]);

  const close = useCallback(() => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setVisible(false), 80);
  }, []);

  // Close on any outside click/tap
  useEffect(() => {
    if (!visible) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (pillRef.current && !pillRef.current.contains(e.target as Node)) {
        setVisible(false);
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [visible]);

  // Close on scroll (tooltip position would be stale)
  useEffect(() => {
    if (!visible) return;
    const handler = () => setVisible(false);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, [visible]);

  return (
    <>
      <span
        ref={pillRef}
        className={`
          inline-block w-full text-[9px] sm:text-[10px] font-medium
          bg-amber-50 text-amber-700 border border-amber-300
          rounded-full px-1.5 py-0.5 leading-none text-center truncate
          ${isTruncated ? "cursor-pointer select-none" : ""}
        `}
        onPointerDown={e => { lastPointerType.current = e.pointerType; }}
        onMouseEnter={() => { if (lastPointerType.current !== "touch") open(); }}
        onMouseLeave={() => { if (lastPointerType.current !== "touch") close(); }}
        onClick={e => {
          if (lastPointerType.current === "touch") {
            // Mobile: only intercept when truncated to preserve card navigation
            if (!isTruncated) return;
            e.preventDefault();
            e.stopPropagation();
            visible ? setVisible(false) : open();
          }
        }}
      >
        {text}
      </span>

      {visible && createPortal(
        <div
          ref={tooltipRef}
          className="
            fixed z-[9999] pointer-events-none
            max-w-[200px] w-max
            bg-zinc-900/90 text-white
            text-[11px] sm:text-[12px] leading-snug font-medium
            rounded-lg px-2.5 py-1.5
          "
          style={{
            top: pos.top,
            left: pos.left,
            transform: pos.above
              ? "translate(-50%, -100%)"
              : "translate(-50%, 0)",
          }}
        >
          {text}
          {/* Small arrow pointer — offset so it always points at the pill */}
          <div
            className={`
              absolute -translate-x-1/2
              w-0 h-0
              border-x-[5px] border-x-transparent
              ${pos.above
                ? "bottom-[-5px] border-t-[5px] border-t-zinc-900/90"
                : "top-[-5px] border-b-[5px] border-b-zinc-900/90"}
            `}
            style={{ left: `calc(50% + ${pos.arrowOffset}px)` }}
          />
        </div>,
        document.body
      )}
    </>
  );
}

function MonsterEvolutionCard({
  monster,
  isCurrent,
  forwardQuery,
  lang,
  levelOnCard,
  conditionOnCard,
}: {
  monster: EvolutionStageMonster;
  isCurrent: boolean;
  forwardQuery: string;
  lang: Lang;
  levelOnCard: number | null;
  conditionOnCard: string | null;
}) {
  const localized = useLocalizedPath();
  const monsterName = pickName(monster as any, lang) || monster.name;

  // CRITICAL: Only show name + form, nothing else!
  // For leader representatives, don't show form name
  const displayName = monster.is_representative
    ? monsterName
    : (monster.form && monster.form !== "default" && monster.form !== "Default")
      ? `${monsterName} (${pickFormName(monster as any, lang) || monster.form})`
      : monsterName;

  const fallbackChain = monsterImageFallbackChain(monster as any, 360);
  const imgSrc = fallbackChain[0] || monsterPlaceholder;

  // CRITICAL: Leader representatives navigate to first (lowest ID) leader form
  const targetId = monster.is_representative && monster.representative_id
    ? monster.representative_id
    : monster.id;

  const hasEvoPills = levelOnCard != null || conditionOnCard != null;

  return (
    <Link
      to={localized(`/dex/monsters/${targetId}`) + `?${forwardQuery}`}
      className={`
        block rounded-lg border-2 bg-white p-2 transition-all duration-200 w-20 sm:w-24
        hover:shadow-lg hover:-translate-y-1
        ${isCurrent
          ? "border-blue-500 shadow-md ring-2 ring-blue-200"
          : "border-zinc-200 hover:border-zinc-400"}
      `}
    >
      <div className="space-y-1 sm:space-y-2">
        {/* Evolution condition pills — inside card, above image, card grows taller naturally */}
        {hasEvoPills && (
          <div className="flex flex-col gap-0.5 items-center">
            {levelOnCard != null && (
              <span className="inline-block text-[9px] sm:text-[10px] font-semibold bg-blue-100 text-blue-700 border border-blue-300 rounded-full px-1.5 py-0.5 leading-none whitespace-nowrap">
                Lv.{levelOnCard}
              </span>
            )}
            {conditionOnCard != null && (
              <ConditionPill text={conditionOnCard} />
            )}
          </div>
        )}

        {/* Image — full size, never shrunk */}
        <div className="relative aspect-square rounded overflow-hidden">
          <img
            src={imgSrc}
            alt={monsterName}
            className="w-full h-full object-contain"
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              const step = Number(img.dataset.fallbackStep || "0");
              const next = step + 1;
              if (next < fallbackChain.length) {
                img.dataset.fallbackStep = String(next);
                img.src = fallbackChain[next]!;
              } else if (img.src !== monsterPlaceholder) {
                img.src = monsterPlaceholder;
              }
            }}
          />

          {/* Current marker (blue dot - no text) */}
          {isCurrent && (
            <div className="absolute bottom-0.5 left-0.5 sm:bottom-1 sm:left-1 w-3 h-3 sm:w-4 sm:h-4 bg-blue-500 rounded-full shadow-sm flex items-center justify-center">
              <div className="w-1 h-1 sm:w-1.5 sm:h-1.5 bg-white rounded-full" />
            </div>
          )}
        </div>

        {/* Name - ONLY name + form, nothing else! */}
        {/* Hidden on mobile (<640px) to save space */}
        <div className="hidden sm:block text-[10px] leading-tight font-medium text-zinc-800 text-center line-clamp-2">
          {displayName}
        </div>
      </div>
    </Link>
  );
}
