import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName } from "@/i18n";
import { typeIconUrl } from "@/lib/images";
import { QUERY_KEYS, LEGACY_TYPES_ORDER } from "@/lib/constants";
import PanelCard from "./PanelCard";
import type { TypeOut, MonsterOut, MonsterLiteOut } from "@/types";

/**
 * Reusable defender-side type matchup panel.
 *
 * Renders the four resistance/weakness rows (3×, 2×, 0.5×, 0.25×) for a
 * monster based on its main_type and (optional) sub_type. Self-contained:
 * fetches /types internally via the shared QUERY_KEYS.TYPES cache, so callers
 * don't need to pass type data in.
 *
 * Algorithm and visual treatment match MonsterDetailPage so the behavior is
 * identical wherever this panel is used.
 */
type MonsterLike = MonsterOut | MonsterLiteOut;

export default function TypeDefensePanel({ monster }: { monster: MonsterLike | null | undefined }) {
  const { lang, t } = useI18n();

  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    staleTime: Infinity,
  });

  // Build name → TypeOut map (TypeOut here is TypeWithMatchupsOut on the wire,
  // i.e. it includes vulnerable_to / resistant_to arrays).
  const typeMap = useMemo(() => {
    const map = new Map<string, TypeOut>();
    (typesQ.data ?? []).forEach((tp) => map.set(tp.name, tp));
    return map;
  }, [typesQ.data]);

  // Defender matchups via set operations on DB-derived relationship data.
  // O(n) where n ≤ 19 — trivially fast, memoized on type names.
  const matchups = useMemo(() => {
    const empty = { triple: [] as string[], double: [] as string[], half: [] as string[], quarter: [] as string[] };
    if (!monster?.main_type || typesQ.data == null || typesQ.data.length === 0) return empty;

    const mainT = typeMap.get(monster.main_type.name);
    if (!mainT) return empty;

    const mainVuln   = new Set<string>(mainT.vulnerable_to ?? []);
    const mainResist = new Set<string>(mainT.resistant_to  ?? []);

    const subT = monster.sub_type ? typeMap.get(monster.sub_type.name) : undefined;
    // Guard against types missing from LEGACY_TYPES_ORDER (e.g. "Leader") so
    // they sort to the END instead of the front. Matches the pattern in
    // MonsterDetailPage's legacy-moves sort.
    const byOrder = (a: string, b: string) => {
      const ia = LEGACY_TYPES_ORDER.indexOf(a as any);
      const ib = LEGACY_TYPES_ORDER.indexOf(b as any);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    };

    if (!subT) {
      return {
        triple:  [],
        double:  [...mainVuln].sort(byOrder),
        half:    [...mainResist].sort(byOrder),
        quarter: [],
      };
    }

    const subVuln   = new Set<string>(subT.vulnerable_to ?? []);
    const subResist = new Set<string>(subT.resistant_to  ?? []);

    const triple:  string[] = [];
    const double:  string[] = [];
    const half:    string[] = [];
    const quarter: string[] = [];

    // 3×: 2× main AND 2× sub
    for (const tp of mainVuln)   if (subVuln.has(tp))                           triple.push(tp);
    // 2×: 2× one, neutral the other (not cancelled by a resist on the other)
    for (const tp of mainVuln)   if (!subVuln.has(tp)   && !subResist.has(tp))   double.push(tp);
    for (const tp of subVuln)    if (!mainVuln.has(tp)  && !mainResist.has(tp))  double.push(tp);
    // 0.25×: 0.5× main AND 0.5× sub
    for (const tp of mainResist) if (subResist.has(tp))                          quarter.push(tp);
    // 0.5×: 0.5× one, neutral the other (not boosted by a vuln on the other)
    for (const tp of mainResist) if (!subResist.has(tp) && !subVuln.has(tp))     half.push(tp);
    for (const tp of subResist)  if (!mainResist.has(tp) && !mainVuln.has(tp))   half.push(tp);

    return {
      triple:  triple.sort(byOrder),
      double:  double.sort(byOrder),
      half:    half.sort(byOrder),
      quarter: quarter.sort(byOrder),
    };
  }, [monster?.main_type?.name, monster?.sub_type?.name, typeMap, typesQ.data]);

  const title = t("dex.typeDefense");

  // No-monster fallback: friendly placeholder rather than an empty card.
  if (!monster?.main_type) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("analysis.noMonsterHint")}</div>
      </PanelCard>
    );
  }

  // Loading: types not yet fetched (extremely brief in practice — usually cached).
  if (typesQ.isLoading || typesQ.data == null) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("common.loading")}</div>
      </PanelCard>
    );
  }

  const renderRow = (key: string, label: string, types: string[], pill: string) =>
    types.length > 0 ? (
      <div key={key} className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <span className={`shrink-0 inline-block text-sm font-semibold rounded-full border px-3 py-1 ${pill}`}>
          {label}
        </span>
        {types.map((name) => {
          const tp = typeMap.get(name);
          const displayName = tp ? pickName(tp as any, lang) : name;
          const iconUrl = typeIconUrl(name, 30);
          return (
            <span
              key={name}
              className="inline-flex items-center gap-1 rounded-full bg-white border border-zinc-200 text-sm px-3 py-1 shadow-sm"
            >
              {iconUrl && (
                <img
                  src={iconUrl}
                  alt=""
                  className="w-5 h-5 sm:w-[22px] sm:h-[22px]"
                  loading="lazy"
                />
              )}
              <span className="font-medium text-zinc-700">{displayName}</span>
            </span>
          );
        })}
      </div>
    ) : null;

  const hasAny =
    matchups.triple.length > 0 ||
    matchups.double.length > 0 ||
    matchups.half.length > 0 ||
    matchups.quarter.length > 0;

  return (
    <PanelCard title={title}>
      {hasAny ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-3">
          <div className="space-y-3">
            {renderRow("triple", t("dex.weaknessTriple"), matchups.triple, "bg-red-50 text-red-700 border-red-200")}
            {renderRow("double", t("dex.weaknessDouble"), matchups.double, "bg-orange-50 text-orange-700 border-orange-200")}
          </div>
          <div className="space-y-3">
            {renderRow("half",    t("dex.resistHalf"),    matchups.half,    "bg-blue-50 text-blue-700 border-blue-200")}
            {renderRow("quarter", t("dex.resistQuarter"), matchups.quarter, "bg-emerald-50 text-emerald-700 border-emerald-200")}
          </div>
        </div>
      ) : (
        <div className="text-sm text-zinc-500">{t("analysis.noMatchupsHint")}</div>
      )}
    </PanelCard>
  );
}
