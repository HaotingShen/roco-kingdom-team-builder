import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName } from "@/i18n";
import { typeIconUrl } from "@/lib/images";
import { QUERY_KEYS } from "@/lib/constants";
import HintPopover from "./HintPopover";
import PanelCard from "./PanelCard";
import {
  DEFENDER_TYPE_NAMES,
  byLegacyTypeOrder,
  byLegacyTypePairOrder,
  groupPairsByAnchor,
  isEffectiveOnNet,
  isResistedOnNet,
  normalizeMoveCategory,
  setsFor,
  type DualGroup,
  type TypeSets,
} from "@/lib/typeEffectiveness";
import type { MoveOut, TypeOut } from "@/types";

/**
 * Reusable offensive coverage panel for a configured monster's selected moves.
 *
 * V3 scope: only attack-category moves (PHY_ATTACK / MAG_ATTACK) are considered.
 * For those moves' types, computes against the 18 base defender types
 * ("Leader" is excluded — it's a legacy meta-type, not a defender):
 *   - effective_union:  defenders where AT LEAST ONE move's type is super-effective
 *   - ineffective_all:  defenders where EVERY move's type is resisted
 *
 * Each row (Effective Against, No Effective Coverage) has its own independent
 * Single|Dual toggle:
 *   - Single: single-type results only
 *   - Dual:   comprehensive view = single-type results PLUS dual-type pair
 *             results where the same condition holds on net effectiveness
 *             (vuln on either type cancels resist on the other)
 *
 * Data flow: the parent passes in the already-fetched `moves` (via the
 * shared `useMovesByIds` hook in MonsterAnalysisPage). The panel still
 * fetches /types itself since TypesQ is unrelated to moves and the query
 * is shared app-wide via QUERY_KEYS.TYPES.
 */

function isAttackCategory(m: MoveOut): boolean {
  // MoveOut declares both move_category and category for defensive parsing —
  // the wire value can be "Physical Attack" / "Magic Attack" / etc. (see
  // normalizeMoveCategory in lib/typeEffectiveness.ts for the mapping).
  const raw = m.move_category || m.category || "";
  const cat = normalizeMoveCategory(raw);
  return cat === "PHY_ATTACK" || cat === "MAG_ATTACK";
}

/**
 * Props for MoveCoveragePanel.
 *
 * `moves` is the already-fetched list of MoveOut (parent uses useMovesByIds).
 * `movesLoading` / `movesError` let the panel render its own loading/error
 * states consistently with when it was self-fetching.
 * `hasSelectedMoves` is true if the slot has at least one non-zero move id —
 * the panel uses it to distinguish "slot has no moves picked" (empty state)
 * from "moves fetched but none are attack moves" (different empty state).
 */
interface Props {
  moves: readonly MoveOut[] | undefined;
  movesLoading: boolean;
  movesError: boolean;
  hasSelectedMoves: boolean;
  initialEffectiveMode?: "single" | "dual";
  initialBlindMode?: "single" | "dual";
  onEffectiveModeChange?: (mode: "single" | "dual") => void;
  onBlindModeChange?: (mode: "single" | "dual") => void;
}

export default function MoveCoveragePanel({
  moves,
  movesLoading,
  movesError,
  hasSelectedMoves,
  initialEffectiveMode,
  initialBlindMode,
  onEffectiveModeChange,
  onBlindModeChange,
}: Props) {
  const { lang, t } = useI18n();

  const [effectiveMode, setEffectiveMode] = useState<"single" | "dual">(initialEffectiveMode ?? "single");
  const [blindMode, setBlindMode] = useState<"single" | "dual">(initialBlindMode ?? "single");

  const handleEffectiveModeChange = (m: "single" | "dual") => { setEffectiveMode(m); onEffectiveModeChange?.(m); };
  const handleBlindModeChange = (m: "single" | "dual") => { setBlindMode(m); onBlindModeChange?.(m); };

  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    staleTime: Infinity,
  });

  // Filter to attack moves with a known move_type.
  const attackMoves = useMemo(() => {
    const list = (moves ?? []).filter(isAttackCategory);
    return list.filter((m) => !!m.move_type?.name);
  }, [moves]);

  const moveTypeNames = useMemo(
    () => attackMoves.map((m) => m.move_type!.name),
    [attackMoves],
  );

  const typeMap = useMemo(() => {
    const map = new Map<string, TypeOut>();
    (typesQ.data ?? []).forEach((tp) => map.set(tp.name, tp));
    return map;
  }, [typesQ.data]);

  // Compute offensive coverage. Vacuously-true guard: do NOT compute when there
  // are zero attack moves, or `every(...)` would mark every type as "all-ineffective".
  // Leader (and any non-defender pseudo-type) is filtered via DEFENDER_TYPE_NAMES.
  const coverage = useMemo(() => {
    const empty = { effectiveUnion: [] as string[], ineffectiveAll: [] as string[] };
    if (moveTypeNames.length === 0 || typesQ.data == null || typesQ.data.length === 0) return empty;

    const effectiveUnion: string[] = [];
    const ineffectiveAll: string[] = [];

    for (const T of typesQ.data) {
      if (!DEFENDER_TYPE_NAMES.has(T.name)) continue; // skip Leader / non-defenders
      const { vuln, resist } = setsFor(T);

      // At least one move's type is super-effective against this defender type.
      if (moveTypeNames.some((name) => vuln.has(name))) effectiveUnion.push(T.name);
      // Every move's type is resisted by this defender type.
      if (moveTypeNames.every((name) => resist.has(name))) ineffectiveAll.push(T.name);
    }

    return {
      effectiveUnion: effectiveUnion.sort(byLegacyTypeOrder),
      ineffectiveAll: ineffectiveAll.sort(byLegacyTypeOrder),
    };
  }, [moveTypeNames, typesQ.data]);

  // Pre-built defender context for the dual-type memos: the 18 valid defender
  // types (Leader filtered out) and their resist/vuln sets. Built once per
  // typesQ.data change so the inner pair loop doesn't re-allocate Sets per call.
  const defenderContext = useMemo(() => {
    if (typesQ.data == null) return null;
    const defenders = typesQ.data.filter((t) => DEFENDER_TYPE_NAMES.has(t.name));
    const sets = new Map<string, TypeSets>();
    for (const tp of defenders) sets.set(tp.name, setsFor(tp));
    return { defenders, sets };
  }, [typesQ.data]);

  // Dual-type blind-spot pairs. (T1, T2) is a blind-spot iff for EVERY move
  // type M the combined effectiveness mult(T1,M) * mult(T2,M) < 1 (i.e. M is
  // resisted on net — at least one type resists and neither is vulnerable).
  //
  // Worst case: 18 defenders → 153 pairs × ≤4 moves × 4 set lookups ≈ 2,500 ops.
  const dualBlindSpots = useMemo<Array<[string, string]>>(() => {
    if (moveTypeNames.length === 0 || defenderContext == null) return [];
    const { defenders, sets } = defenderContext;

    const pairs: Array<[string, string]> = [];
    for (let i = 0; i < defenders.length; i++) {
      const t1 = defenders[i]!;
      const s1 = sets.get(t1.name)!;
      for (let j = i + 1; j < defenders.length; j++) {
        const t2 = defenders[j]!;
        const s2 = sets.get(t2.name)!;
        if (moveTypeNames.every((m) => isResistedOnNet(s1, s2, m))) {
          // Canonicalize ordering so display is independent of typesQ.data order.
          pairs.push(
            byLegacyTypeOrder(t1.name, t2.name) <= 0
              ? [t1.name, t2.name]
              : [t2.name, t1.name],
          );
        }
      }
    }
    return pairs.sort(byLegacyTypePairOrder);
  }, [moveTypeNames, defenderContext]);

  // Compact display form: collapse Steel+Fire, Steel+Water, ... into one
  // anchor-keyed group "Steel + Fire/Water/...". Anchor priority is the
  // single-type blind list (so types that are *already* a problem alone
  // become the anchor and the row reads as "Steel is blind, AND so is
  // Steel paired with these").
  const groupedDualBlindSpots = useMemo<DualGroup[]>(() => {
    const single = new Set<string>(coverage.ineffectiveAll);
    return groupPairsByAnchor(dualBlindSpots, single);
  }, [dualBlindSpots, coverage.ineffectiveAll]);

  // Dual-type effective coverage. (T1, T2) is "effectively covered" iff at
  // least ONE move type M is super-effective on net (at least one type is
  // vulnerable and neither resists). Same complexity profile as above.
  const dualEffectiveCoverage = useMemo<Array<[string, string]>>(() => {
    if (moveTypeNames.length === 0 || defenderContext == null) return [];
    const { defenders, sets } = defenderContext;

    const pairs: Array<[string, string]> = [];
    for (let i = 0; i < defenders.length; i++) {
      const t1 = defenders[i]!;
      const s1 = sets.get(t1.name)!;
      for (let j = i + 1; j < defenders.length; j++) {
        const t2 = defenders[j]!;
        const s2 = sets.get(t2.name)!;
        if (moveTypeNames.some((m) => isEffectiveOnNet(s1, s2, m))) {
          pairs.push(
            byLegacyTypeOrder(t1.name, t2.name) <= 0
              ? [t1.name, t2.name]
              : [t2.name, t1.name],
          );
        }
      }
    }
    return pairs.sort(byLegacyTypePairOrder);
  }, [moveTypeNames, defenderContext]);

  // Compact display form for the effective row, mirroring the blind row.
  // Anchor priority is `coverage.effectiveUnion` so types that are already
  // covered alone anchor any pairs containing them.
  const groupedDualEffectiveCoverage = useMemo<DualGroup[]>(() => {
    const single = new Set<string>(coverage.effectiveUnion);
    return groupPairsByAnchor(dualEffectiveCoverage, single);
  }, [dualEffectiveCoverage, coverage.effectiveUnion]);

  // Outer card shell is now the shared PanelCard component. Three of the
  // analysis-surface panels render with the same title+body shape; this
  // keeps them in lockstep.
  const title = t("analysis.moveCoverage");

  // Loading: any required data still in flight.
  if (movesLoading || typesQ.isLoading) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("common.loading")}</div>
      </PanelCard>
    );
  }

  // Required data unavailable (fetch errored or returned empty).
  if (movesError || typesQ.isError || typesQ.data == null) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-rose-600">{t("analysis.coverageDataUnavailable")}</div>
      </PanelCard>
    );
  }

  // No selected moves at all (slot has 0 moves picked yet).
  if (!hasSelectedMoves) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("analysis.noAttackMoves")}</div>
      </PanelCard>
    );
  }

  // Moves loaded but none of them are in attack categories.
  if (attackMoves.length === 0) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("analysis.noAttackMoves")}</div>
      </PanelCard>
    );
  }

  // ── Render helpers ────────────────────────────────────────────────────
  // Both Effective and Blind rows share the same shape: row label, mode
  // toggle, then a flat list of pills (single-type icon pills, plus dual-type
  // pair pills when in "dual" mode). These small helpers keep the inline JSX
  // below readable and avoid per-row duplication.

  const renderToggle = (
    mode: "single" | "dual",
    setMode: (m: "single" | "dual") => void,
  ) => (
    <div className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-50 p-0.5 text-sm">
      {(["single", "dual"] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => setMode(m)}
          aria-pressed={mode === m}
          className={`px-3 py-1 rounded-full transition-colors cursor-pointer ${
            mode === m
              ? "bg-white text-zinc-800 shadow-sm font-medium"
              : "text-zinc-500 hover:text-zinc-700"
          }`}
        >
          {m === "single" ? t("analysis.blindSpotModeSingle") : t("analysis.blindSpotModeDual")}
        </button>
      ))}
    </div>
  );

  const renderSinglePill = (name: string) => {
    const tp = typeMap.get(name);
    const displayName = tp ? pickName(tp, lang) : name;
    const iconUrl = typeIconUrl(name, 30);
    return (
      <span
        key={name}
        className="inline-flex items-center gap-1 rounded-full bg-white border border-zinc-200 text-sm px-3 py-1 shadow-sm"
      >
        {iconUrl && (
          <img src={iconUrl} alt="" className="w-5 h-5 sm:w-[22px] sm:h-[22px] shrink-0" loading="lazy" />
        )}
        <span className="font-medium text-zinc-700 leading-none">{displayName}</span>
      </span>
    );
  };

  // Compact dual-group pill: anchor type shown with icon + name; partner
  // types shown as icons only (with hover/alt text for accessibility) so a
  // group like "Steel + Fire/Water/Grass/.../Bug" stays on one line instead
  // of producing N separate pills.
  const renderDualGroup = ({ anchor, partners }: DualGroup) => {
    const aTp = typeMap.get(anchor);
    const aName = aTp ? pickName(aTp, lang) : anchor;
    const aIcon = typeIconUrl(anchor, 30);
    return (
      <span
        key={`group:${anchor}`}
        className="inline-flex flex-wrap items-center gap-1 rounded-xl bg-white border border-zinc-200 text-sm px-3 py-1 shadow-sm max-w-full"
      >
        {aIcon && (
          <img src={aIcon} alt="" className="w-5 h-5 sm:w-[22px] sm:h-[22px] shrink-0" loading="lazy" />
        )}
        {/* leading-none collapses the default 1.5 line-height so the text
            doesn't add extra height above/below and stays centered with the
            fixed-pixel icons. */}
        <span className="font-medium text-zinc-700 leading-none">{aName}</span>
        <span className="text-zinc-400 leading-none">+</span>
        {partners.map((p, i) => {
          const pTp = typeMap.get(p);
          const pName = pTp ? pickName(pTp, lang) : p;
          const pIcon = typeIconUrl(p, 30);
          const sep =
            i > 0 ? (
              <span key={`${p}-sep`} aria-hidden className="text-zinc-300 leading-none select-none">
                /
              </span>
            ) : null;
          return pIcon ? (
            <Fragment key={p}>
              {sep}
              <img
                src={pIcon}
                alt={pName}
                title={pName}
                className="w-5 h-5 sm:w-[22px] sm:h-[22px] shrink-0"
                loading="lazy"
              />
            </Fragment>
          ) : (
            <Fragment key={p}>
              {sep}
              <span className="font-medium text-zinc-700 leading-none">{pName}</span>
            </Fragment>
          );
        })}
      </span>
    );
  };

  // Each mode is fully independent: single mode shows only single-type results,
  // dual mode shows only dual-type pair results. The two toggles answer different
  // questions — no mixing, no separator needed.
  const dualBlindGroupCount = groupedDualBlindSpots.length;
  const dualEffectiveGroupCount = groupedDualEffectiveCoverage.length;

  return (
    <PanelCard title={title}>
      <div className="space-y-3">
        {/* Effective Against row */}
        <div className="space-y-1.5">
          {/* Header: label + hint + toggle — wraps if screen is too narrow for all three */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="shrink-0 inline-block text-sm font-semibold rounded-full border px-3 py-1 bg-emerald-50 text-emerald-700 border-emerald-200">
              {t("analysis.coverageEffective")}
            </span>
            <HintPopover
              text={effectiveMode === "single" ? t("analysis.coverageEffectiveHintSingle") : t("analysis.coverageEffectiveHintDual")}
              ariaLabel={t("analysis.coverageEffective")}
            />
            {renderToggle(effectiveMode, handleEffectiveModeChange)}
          </div>
          {/* Pills on their own line, always wrapping cleanly */}
          <div className="flex flex-wrap gap-1.5">
            {effectiveMode === "single" && coverage.effectiveUnion.map(renderSinglePill)}
            {effectiveMode === "dual" && groupedDualEffectiveCoverage.map(renderDualGroup)}
            {effectiveMode === "single" && coverage.effectiveUnion.length === 0 && (
              <span className="text-xs text-zinc-500">{t("analysis.noEffectiveCoverage")}</span>
            )}
            {effectiveMode === "dual" && dualEffectiveGroupCount === 0 && (
              <span className="text-xs text-zinc-500">{t("analysis.noEffectiveCoverageDual")}</span>
            )}
          </div>
          {effectiveMode === "dual" && dualEffectiveGroupCount > 0 && (
            <p className="text-[10px] text-zinc-400 pl-1">{t("analysis.dualListCompleteEffective")}</p>
          )}
        </div>

        {/* No Effective Coverage (blind spot) row */}
        <div className="space-y-1.5">
          {/* Header: label + hint + toggle — wraps if screen is too narrow for all three */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="shrink-0 inline-block text-sm font-semibold rounded-full border px-3 py-1 bg-red-50 text-red-700 border-red-200">
              {t("analysis.coverageBlindSpot")}
            </span>
            <HintPopover
              text={blindMode === "single" ? t("analysis.coverageBlindSpotHintSingle") : t("analysis.coverageBlindSpotHintDual")}
              ariaLabel={t("analysis.coverageBlindSpot")}
            />
            {renderToggle(blindMode, handleBlindModeChange)}
          </div>
          {/* Pills on their own line, always wrapping cleanly */}
          <div className="flex flex-wrap gap-1.5">
            {blindMode === "single" && coverage.ineffectiveAll.map(renderSinglePill)}
            {blindMode === "dual" && groupedDualBlindSpots.map(renderDualGroup)}
            {blindMode === "single" && coverage.ineffectiveAll.length === 0 && (
              <span className="text-xs text-zinc-500">{t("analysis.noBlindSpots")}</span>
            )}
            {blindMode === "dual" && dualBlindGroupCount === 0 && (
              <span className="text-xs text-zinc-500">{t("analysis.noBlindSpotsDual")}</span>
            )}
          </div>
          {blindMode === "dual" && dualBlindGroupCount > 0 && (
            <p className="text-[10px] text-zinc-400 pl-1">{t("analysis.dualListCompleteBlindSpot")}</p>
          )}
        </div>
      </div>
    </PanelCard>
  );
}
