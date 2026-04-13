import { Link, useParams } from "react-router-dom";
import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickFormName } from "@/i18n";
import { QUERY_KEYS } from "@/lib/constants";
import { useBuilderStore } from "./builderStore";
import MonsterInspector from "./MonsterInspector";
import PageTabs from "@/components/PageTabs";
import TypeDefensePanel from "@/components/TypeDefensePanel";
import MoveCoveragePanel from "@/components/MoveCoveragePanel";
import EffectiveStatsPanel from "@/components/EffectiveStatsPanel";
import type { MonsterOut, MonsterLiteOut, TypeOut } from "@/types";

/**
 * Builder-scoped analysis page for a single configured monster slot.
 *
 * The slot index in the URL is the source identity. The actual monster +
 * config (personality, legacy type, moves, talents) is read from the builder
 * store via useBuilderStore — NOT from a URL monster id. This means the page
 * always reflects the user's in-builder configuration and updates live as
 * they edit the monster on the left side.
 *
 * Leader Form Toggle (view-only):
 *   Shown when the slot's monster has leader_potential=true AND the user has
 *   selected the Leader legacy type for that slot. Switching to Leader form
 *   only affects EffectiveStatsPanel (different base stats) — TypeDefensePanel
 *   always shows the regular form's types because leader forms share the same
 *   elemental typing as their pre-evolution final stage. MoveCoveragePanel is
 *   also unaffected (uses user's chosen moves). The builder store is never modified.
 */
export default function MonsterAnalysisPage() {
  const { slot: slotParam } = useParams();
  const { t, lang } = useI18n();
  const slots = useBuilderStore((s) => s.slots);

  const slotIdx = Number(slotParam);
  const validSlot =
    Number.isInteger(slotIdx) && slotIdx >= 0 && slotIdx < slots.length;
  const slot = validSlot ? slots[slotIdx] : null;
  const monsterId = slot?.monster_id ?? 0;

  // Leader form toggle state — resets whenever the user navigates to a different slot.
  const [showLeaderForm, setShowLeaderForm] = useState(false);
  useEffect(() => { setShowLeaderForm(false); }, [slotIdx]);

  // Fetch monster detail with the SAME query key the inspector uses, so the
  // cache is shared (no extra network call when navigating from /build).
  const monsterQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(monsterId),
    queryFn: () => endpoints.monsterById(monsterId).then((r) => r.data),
    enabled: !!monsterId,
  });

  // Types list — needed to resolve the Leader type ID.
  // Uses the same cache key as TypeDefensePanel/MoveCoveragePanel; zero extra network calls.
  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    staleTime: Infinity,
  });

  // Leader type ID resolved by name — avoids hardcoding a DB ID.
  const leaderTypeId = useMemo(
    () => typesQ.data?.find((tp) => tp.name === "Leader")?.id ?? null,
    [typesQ.data],
  );

  const detail: MonsterOut | undefined = monsterQ.data;

  // Step 1 — find the leader form record for this exact monster form.
  // Using evolves_from_id (not species_id) is critical for multi-form species:
  // e.g. Yajiri-Fluffy (id=15) → Yajiking-Fluffy (evolves_from=15), not Yajiking-Compact.
  // Returns MonsterLiteOut (list endpoint) — only used here to get the leader's id.
  const leaderInfoQ = useQuery({
    queryKey: QUERY_KEYS.LEADER_MONSTER(detail?.id ?? 0),
    queryFn: () =>
      endpoints
        .monsters({ evolves_from_id: detail!.id, is_leader_form: true })
        .then((r) => ((r.data as MonsterLiteOut[])[0] ?? null)),
    enabled: !!detail?.leader_potential && !!detail?.id,
    staleTime: Infinity,
  });

  // Step 2 — fetch the full MonsterOut for the leader so EffectiveStatsPanel
  // gets properly typed, non-nullable base stats.
  const leaderDetailQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(leaderInfoQ.data?.id ?? 0),
    queryFn: () =>
      endpoints.monsterById(leaderInfoQ.data!.id).then((r) => r.data as MonsterOut),
    enabled: !!leaderInfoQ.data?.id,
    staleTime: Infinity,
  });

  // Toggle is shown only when ALL conditions hold.
  const showLeaderToggle =
    !!detail?.leader_potential &&
    leaderTypeId !== null &&
    slot?.legacy_type_id === leaderTypeId &&
    leaderDetailQ.data != null &&
    !leaderDetailQ.isLoading;

  // Only EffectiveStatsPanel switches monster on toggle — TypeDefensePanel
  // always uses `detail` because leader forms share the same elemental typing.
  const activeStatsMonster: MonsterOut | undefined =
    showLeaderForm && leaderDetailQ.data ? leaderDetailQ.data : detail;

  // Match MonsterDetailPage's behavior: scroll to top whenever the slot changes.
  useEffect(() => { window.scrollTo(0, 0); }, [slotParam]);

  // Empty / invalid state: bad slot index OR slot has no monster picked yet.
  if (!validSlot || !monsterId) {
    return (
      <div className="space-y-3">
        <div className="flex items-center">
          <Link
            to="/build"
            className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
          >
            <span aria-hidden className="text-xl leading-none text-zinc-600 -translate-y-[1px]">←</span>
            <span className="text-zinc-700">{t("dex.backToBuilder")}</span>
          </Link>
        </div>

        <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-8 text-center">
          <div className="text-lg font-semibold text-zinc-800 mb-2">
            {t("analysis.emptyTitle")}
          </div>
          <div className="text-sm text-zinc-600 mb-4">
            {t("analysis.emptyHint")}
          </div>
          <Link
            to="/build"
            className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
          >
            {t("dex.backToBuilder")}
          </Link>
        </section>
      </div>
    );
  }

  // Leader Form Toggle row — only rendered when showLeaderToggle is true.
  const leaderToggle = showLeaderToggle ? (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {/* Pill toggle */}
      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`text-sm cursor-pointer select-none transition-colors duration-150 ${
            !showLeaderForm ? "font-semibold text-zinc-800" : "text-zinc-400"
          }`}
          onClick={() => setShowLeaderForm(false)}
        >
          {t("analysis.regularForm")}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={showLeaderForm}
          onClick={() => setShowLeaderForm((v) => !v)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
            showLeaderForm ? "bg-indigo-500" : "bg-zinc-300"
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
              showLeaderForm ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
        <span
          className={`text-sm cursor-pointer select-none transition-colors duration-150 ${
            showLeaderForm ? "font-semibold text-zinc-800" : "text-zinc-400"
          }`}
          onClick={() => setShowLeaderForm(true)}
        >
          {t("analysis.leaderForm")}
        </span>
      </div>
      {/* Explanatory note — shows active leader form name when toggle is ON */}
      <span className="text-xs text-zinc-500 leading-tight">
        {showLeaderForm && leaderDetailQ.data
          ? (() => {
              const lm = leaderDetailQ.data;
              const name = pickName(lm, lang) || lm.name;
              const form = pickFormName(lm, lang);
              return (t("analysis.leaderFormActive") ?? "Viewing: {name}").replace(
                "{name}",
                form ? `${name} (${form})` : name,
              );
            })()
          : t("analysis.leaderFormNote")}
      </span>
    </div>
  ) : null;

  // Tab 1 content with explicit loading + error states.
  // Without these, TypeDefensePanel falls back to its "noMonsterHint" placeholder
  // while monsterQ is in flight, which is misleading right after clicking Analyze.
  const statsTabContent = monsterQ.isLoading ? (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
      <div className="text-sm text-zinc-500">{t("common.loading")}</div>
    </section>
  ) : monsterQ.isError ? (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
      <div className="text-sm text-rose-600">{t("analysis.loadFailed")}</div>
    </section>
  ) : (
    <div className="space-y-3">
      {leaderToggle}
      {/* TypeDefensePanel always uses the regular form — leader forms share the same typing. */}
      <TypeDefensePanel monster={detail} />
      <MoveCoveragePanel
        moveIds={[slot?.move1_id, slot?.move2_id, slot?.move3_id, slot?.move4_id]}
      />
      <EffectiveStatsPanel
        monster={activeStatsMonster}
        talent={slot?.talent ?? {
          hp_boost: 0, phy_atk_boost: 0, mag_atk_boost: 0,
          phy_def_boost: 0, mag_def_boost: 0, spd_boost: 0,
        }}
        personalityId={slot?.personality_id ?? 0}
      />
    </div>
  );

  const tabs = [
    {
      key: "stats",
      label: t("analysis.tabStats"),
      content: statsTabContent,
    },
    {
      key: "vsFeatured",
      label: t("analysis.tabVsFeatured"),
      content: (
        <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-6">
          <div className="text-sm font-semibold text-zinc-800 mb-2">
            {t("analysis.tabVsFeatured")}
          </div>
          <div className="text-sm text-zinc-600">
            {t("analysis.vsFeaturedComingSoon")}
          </div>
        </section>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center">
        <Link
          to="/build"
          className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
        >
          <span aria-hidden className="text-xl leading-none text-zinc-600 -translate-y-[1px]">←</span>
          <span className="text-zinc-700">{t("dex.backToBuilder")}</span>
        </Link>
      </div>

      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[340px_1fr] xl:grid-cols-[420px_1fr]">
        <div>
          <MonsterInspector
            activeIdx={slotIdx}
            context="analyze"
            dexMonsterId={showLeaderForm && leaderDetailQ.data ? leaderDetailQ.data.id : undefined}
          />
        </div>
        <div>
          <PageTabs tabs={tabs} />
        </div>
      </div>
    </div>
  );
}
