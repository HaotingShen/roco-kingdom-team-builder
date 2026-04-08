import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName } from "@/i18n";
import { typeIconUrl } from "@/lib/images";
import { QUERY_KEYS } from "@/lib/constants";
import {
  DEFENDER_TYPE_NAMES,
  byLegacyTypeOrder,
  byLegacyTypePairOrder,
  groupPairsByAnchor,
  isEffectiveOnNet,
  isResistedOnNet,
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
 * Self-contained: takes the slot's 4 move IDs and fetches everything itself,
 * sharing react-query caches with the rest of the app (moves-by-ids + types).
 */

// Matches the existing inline pattern used in MonsterDetailPage / DexPage / MoveDetailPage.
// Wire format from the backend is "Physical Attack" / "Magic Attack" / "Defense" / "Status";
// the rest of the frontend uses "PHY_ATTACK" / "MAG_ATTACK" / "DEFENSE" / "STATUS".
function normalizeMoveCategory(category: string): string {
  const upper = category.toUpperCase();
  if (upper === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (upper === "MAGIC ATTACK") return "MAG_ATTACK";
  return upper;
}

function isAttackCategory(m: MoveOut): boolean {
  // MoveOut declares both move_category and category for defensive parsing —
  // the wire value can be "Physical Attack" / "Magic Attack" / etc. (see notes
  // on normalizeMoveCategory above).
  const raw = m.move_category || m.category || "";
  const cat = normalizeMoveCategory(raw);
  return cat === "PHY_ATTACK" || cat === "MAG_ATTACK";
}

export default function MoveCoveragePanel({ moveIds }: { moveIds: Array<number | 0 | undefined | null> }) {
  const { lang, t } = useI18n();

  // V3: each coverage row has its own independent Single|Dual toggle.
  // Both default to "single" for backward compatibility — anyone who already
  // learned the panel sees no change until they click. In "dual" mode the row
  // shows a comprehensive view: single-type results PLUS dual-type results.
  const [effectiveMode, setEffectiveMode] = useState<"single" | "dual">("single");
  const [blindMode, setBlindMode] = useState<"single" | "dual">("single");

  // Dedupe + drop falsy IDs (slot.moveN_id is 0 when unset).
  const uniqIds = useMemo(
    () => Array.from(new Set(moveIds.filter((x): x is number => typeof x === "number" && x > 0))),
    [moveIds],
  );

  const movesQ = useQuery({
    queryKey: ["moves-by-ids", uniqIds.join(",")],
    queryFn: () =>
      endpoints
        .moves({ ids: uniqIds.join(",") })
        .then((r) => (r.data?.items ?? r.data) as MoveOut[]),
    enabled: uniqIds.length > 0,
  });

  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  // Filter to attack moves with a known move_type.
  const attackMoves = useMemo(() => {
    const list = (movesQ.data ?? []).filter(isAttackCategory);
    return list.filter((m) => !!m.move_type?.name);
  }, [movesQ.data]);

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

  // Outer card shell — kept identical to TypeDefensePanel for visual rhythm.
  const card = (body: React.ReactNode) => (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg font-semibold text-zinc-800">{t("analysis.moveCoverage")}</span>
      </div>
      {body}
    </section>
  );

  // Loading: any required data still in flight.
  if (movesQ.isLoading || typesQ.isLoading) {
    return card(<div className="text-sm text-zinc-500">{t("common.loading")}</div>);
  }

  // Required data unavailable (fetch errored or returned empty).
  if (movesQ.isError || typesQ.isError || typesQ.data == null) {
    return card(<div className="text-sm text-rose-600">{t("analysis.coverageDataUnavailable")}</div>);
  }

  // No selected moves at all (slot has 0 moves picked yet).
  if (uniqIds.length === 0) {
    return card(<div className="text-sm text-zinc-500">{t("analysis.noAttackMoves")}</div>);
  }

  // Moves loaded but none of them are in attack categories.
  if (attackMoves.length === 0) {
    return card(<div className="text-sm text-zinc-500">{t("analysis.noAttackMoves")}</div>);
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
    <div className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-50 p-0.5 text-xs sm:text-sm">
      {(["single", "dual"] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => setMode(m)}
          aria-pressed={mode === m}
          className={`px-2.5 sm:px-3 py-0.5 sm:py-1 rounded-full transition-colors ${
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
        className="inline-flex items-center gap-1 rounded-full bg-white border border-zinc-200 text-xs sm:text-sm px-2.5 sm:px-3 py-0.5 sm:py-1 shadow-sm"
      >
        {iconUrl && (
          <img src={iconUrl} alt="" className="w-[18px] h-[18px] sm:w-[22px] sm:h-[22px]" loading="lazy" />
        )}
        <span className="font-medium text-zinc-700">{displayName}</span>
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
        className="inline-flex items-center gap-1 rounded-full bg-white border border-zinc-200 text-xs sm:text-sm px-2.5 sm:px-3 py-0.5 sm:py-1 shadow-sm"
      >
        {aIcon && (
          <img src={aIcon} alt="" className="w-[18px] h-[18px] sm:w-[22px] sm:h-[22px]" loading="lazy" />
        )}
        <span className="font-medium text-zinc-700">{aName}</span>
        <span className="text-zinc-400">+</span>
        {partners.map((p) => {
          const pTp = typeMap.get(p);
          const pName = pTp ? pickName(pTp, lang) : p;
          const pIcon = typeIconUrl(p, 30);
          return pIcon ? (
            <img
              key={p}
              src={pIcon}
              alt={pName}
              title={pName}
              className="w-[18px] h-[18px] sm:w-[22px] sm:h-[22px]"
              loading="lazy"
            />
          ) : (
            <span key={p} className="font-medium text-zinc-700">
              {pName}
            </span>
          );
        })}
      </span>
    );
  };

  // Empty-state helper: in "dual" mode the row is empty only when BOTH
  // single- and dual-type result lists are empty (the dual view includes
  // single results). In "single" mode, only the single list matters.
  const showEmptyHint = (
    mode: "single" | "dual",
    singleCount: number,
    dualCount: number,
  ) => singleCount === 0 && (mode === "single" || dualCount === 0);

  // Visual separator dot between single-type and dual-type pill groups in
  // dual mode. Only rendered when BOTH groups have content — keeps the row
  // visually segmented at scale (worst case dozens of dual pills) without
  // adding clutter when one side is empty.
  const renderGroupSeparator = (
    mode: "single" | "dual",
    singleCount: number,
    dualCount: number,
  ) =>
    mode === "dual" && singleCount > 0 && dualCount > 0 ? (
      <span aria-hidden className="text-zinc-300 px-1 select-none">·</span>
    ) : null;

  // Length sources for empty/separator decisions in dual mode: groups of
  // anchor-keyed dual results, NOT raw pair counts. A row with one group of
  // 12 partners is "1 result", visually — and the empty hint should respect
  // that, not the underlying pair count.
  const dualBlindGroupCount = groupedDualBlindSpots.length;
  const dualEffectiveGroupCount = groupedDualEffectiveCoverage.length;

  return card(
    <div className="space-y-3">
      {/* Effective Against row */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <span className="shrink-0 inline-block text-xs sm:text-sm font-semibold rounded-full border px-2.5 sm:px-3 py-1 bg-emerald-50 text-emerald-700 border-emerald-200">
          {t("analysis.coverageEffective")}
        </span>
        {renderToggle(effectiveMode, setEffectiveMode)}
        {coverage.effectiveUnion.map(renderSinglePill)}
        {renderGroupSeparator(effectiveMode, coverage.effectiveUnion.length, dualEffectiveGroupCount)}
        {effectiveMode === "dual" && groupedDualEffectiveCoverage.map(renderDualGroup)}
        {showEmptyHint(effectiveMode, coverage.effectiveUnion.length, dualEffectiveGroupCount) && (
          <span className="text-xs text-zinc-500">{t("analysis.noEffectiveCoverage")}</span>
        )}
      </div>

      {/* No Effective Coverage (blind spot) row */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <span className="shrink-0 inline-block text-xs sm:text-sm font-semibold rounded-full border px-2.5 sm:px-3 py-1 bg-red-50 text-red-700 border-red-200">
          {t("analysis.coverageBlindSpot")}
        </span>
        {renderToggle(blindMode, setBlindMode)}
        {coverage.ineffectiveAll.map(renderSinglePill)}
        {renderGroupSeparator(blindMode, coverage.ineffectiveAll.length, dualBlindGroupCount)}
        {blindMode === "dual" && groupedDualBlindSpots.map(renderDualGroup)}
        {showEmptyHint(blindMode, coverage.ineffectiveAll.length, dualBlindGroupCount) && (
          <span className="text-xs text-zinc-500">{t("analysis.noBlindSpots")}</span>
        )}
      </div>
    </div>,
  );
}
