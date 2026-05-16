import { useMemo, useState, useEffect, useRef } from "react";
import { useI18n, pickName } from "@/i18n";
import { getAttackerStatusOptions } from "@/lib/attackerStatusOptions";
import type { MoveOut } from "@/types";

interface Props {
  moves: readonly MoveOut[];
  activeStatusIds: readonly number[];
  onChange: (ids: number[]) => void;
  monsterName?: string;
}

/**
 * Multi-select attacker status toggle used by the vs-featured-teams matchup.
 *
 * "Original" is the zero-status state. Selecting it clears every status;
 * selecting any status implicitly leaves Original.
 */
export default function AttackerStatusSelector({
  moves,
  activeStatusIds,
  onChange,
  monsterName,
}: Props) {
  const { lang, t } = useI18n();
  const activeIds = useMemo(() => new Set(activeStatusIds), [activeStatusIds]);
  const [hintOpen, setHintOpen] = useState(false);
  const [flipDown, setFlipDown] = useState(false);
  const hintRef = useRef<HTMLSpanElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!hintOpen) return;
    const close = (e: MouseEvent) => {
      if (hintRef.current && !hintRef.current.contains(e.target as Node)) setHintOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [hintOpen]);

  const openHint = () => {
    if (btnRef.current) {
      // Flip tooltip below if less than 300px above the button in the viewport.
      // 300px accounts for the topbar + optional MY FORM block above this component,
      // and avoids the tooltip being clipped by the left column's overflow-y:auto boundary.
      setFlipDown(btnRef.current.getBoundingClientRect().top < 220);
    }
    setHintOpen((v) => !v);
  };

  const options = useMemo(() => getAttackerStatusOptions(moves), [moves]);

  const toggleStatus = (statusId: number) => {
    const next = new Set(activeStatusIds);
    if (next.has(statusId)) {
      next.delete(statusId);
    } else {
      next.add(statusId);
    }
    onChange(Array.from(next));
  };

  return (
    <div className="lg:sticky lg:top-0 z-[9] rounded-lg border border-zinc-200 bg-white/95 px-3 py-2.5 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/85 border-l-4 border-l-indigo-400">
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-sm font-semibold text-zinc-800">
          {t("analysis.matchupMyJinglingStatus")}
        </span>
        {monsterName && (
          <span className="text-sm text-zinc-800 font-normal">· {monsterName}</span>
        )}
        <span ref={hintRef} className="relative ml-auto shrink-0">
          <button
            ref={btnRef}
            type="button"
            onClick={openHint}
            className="w-5 h-5 rounded-full border border-zinc-300 bg-white text-zinc-400 hover:text-zinc-600 hover:border-zinc-400 text-xs font-bold leading-none flex items-center justify-center cursor-pointer transition-colors"
            aria-label="Help"
          >
            ?
          </button>
          {hintOpen && (
            <span className={`absolute z-20 right-0 w-64 rounded-md bg-zinc-800 px-2.5 py-2 text-xs leading-snug text-white shadow-lg ${flipDown ? "top-full mt-2" : "bottom-full mb-2"}`}>
              {t("analysis.matchupMyJinglingStatusHint")}
              <span className={`absolute right-3 border-4 border-transparent ${flipDown ? "bottom-full border-b-zinc-800" : "top-full border-t-zinc-800"}`} />
            </span>
          )}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => onChange([])}
          aria-pressed={activeStatusIds.length === 0}
          className={`inline-flex items-center text-xs rounded-full border px-2.5 py-1 transition-colors cursor-pointer ${
            activeStatusIds.length === 0
              ? "bg-zinc-800 text-white border-zinc-800 shadow-sm"
              : "bg-white text-zinc-700 border-zinc-300 hover:bg-zinc-50 hover:border-zinc-400"
          }`}
        >
          {t("analysis.matchupOriginal")}
        </button>

        {options.map((status) => {
          const active = activeIds.has(status.id);
          return (
            <button
              key={status.id}
              type="button"
              onClick={() => toggleStatus(status.id)}
              aria-pressed={active}
              className={`inline-flex items-center text-xs rounded-full border px-2.5 py-1 transition-colors cursor-pointer ${
                active
                  ? "bg-zinc-800 text-white border-zinc-800 shadow-sm"
                  : "bg-white text-zinc-700 border-zinc-300 hover:bg-zinc-50 hover:border-zinc-400"
              }`}
            >
              {pickName(status, lang) || status.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
