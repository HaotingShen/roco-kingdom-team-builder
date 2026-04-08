import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName } from "@/i18n";
import { typeIconUrl } from "@/lib/images";
import { QUERY_KEYS, LEGACY_TYPES_ORDER } from "@/lib/constants";
import type { MoveOut, TypeOut } from "@/types";

/**
 * Reusable offensive coverage panel for a configured monster's selected moves.
 *
 * V2 scope: only attack-category moves (PHY_ATTACK / MAG_ATTACK) are considered.
 * For those moves' types, computes against the 19 base defender types:
 *   - effective_union:  defenders where AT LEAST ONE move's type is super-effective
 *   - ineffective_all:  defenders where EVERY move's type is resisted
 *
 * Single-type defenders only (no dual-type combinations) per V2 spec.
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
  const coverage = useMemo(() => {
    const empty = { effectiveUnion: [] as string[], ineffectiveAll: [] as string[] };
    if (moveTypeNames.length === 0 || typesQ.data == null || typesQ.data.length === 0) return empty;

    // Guard against types missing from LEGACY_TYPES_ORDER (e.g. "Leader") so
    // they sort to the END instead of the front. Matches the pattern in
    // MonsterDetailPage's legacy-moves sort.
    const byOrder = (a: string, b: string) => {
      const ia = LEGACY_TYPES_ORDER.indexOf(a as any);
      const ib = LEGACY_TYPES_ORDER.indexOf(b as any);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    };

    const effectiveUnion: string[] = [];
    const ineffectiveAll: string[] = [];

    for (const T of typesQ.data) {
      const vuln = new Set<string>(T.vulnerable_to ?? []);
      const resist = new Set<string>(T.resistant_to ?? []);

      // At least one move's type is super-effective against this defender type.
      if (moveTypeNames.some((name) => vuln.has(name))) effectiveUnion.push(T.name);
      // Every move's type is resisted by this defender type.
      if (moveTypeNames.every((name) => resist.has(name))) ineffectiveAll.push(T.name);
    }

    return {
      effectiveUnion: effectiveUnion.sort(byOrder),
      ineffectiveAll: ineffectiveAll.sort(byOrder),
    };
  }, [moveTypeNames, typesQ.data]);

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

  const renderRow = (key: string, label: string, types: string[], pill: string, emptyHint: string) => (
    <div key={key} className="flex flex-wrap items-center gap-x-2 gap-y-2">
      <span className={`shrink-0 inline-block text-xs sm:text-sm font-semibold rounded-full border px-2.5 sm:px-3 py-1 ${pill}`}>
        {label}
      </span>
      {types.length > 0 ? (
        types.map((name) => {
          const tp = typeMap.get(name);
          const displayName = tp ? pickName(tp as any, lang) : name;
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
        })
      ) : (
        <span className="text-xs text-zinc-500">{emptyHint}</span>
      )}
    </div>
  );

  return card(
    <div className="space-y-3">
      {renderRow(
        "effective",
        t("analysis.coverageEffective"),
        coverage.effectiveUnion,
        "bg-emerald-50 text-emerald-700 border-emerald-200",
        t("analysis.noEffectiveCoverage"),
      )}
      {renderRow(
        "blindspot",
        t("analysis.coverageBlindSpot"),
        coverage.ineffectiveAll,
        "bg-red-50 text-red-700 border-red-200",
        t("analysis.noBlindSpots"),
      )}
    </div>,
  );
}
