import { Link, useParams } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import { QUERY_KEYS } from "@/lib/constants";
import { useBuilderStore } from "./builderStore";
import MonsterInspector from "./MonsterInspector";
import PageTabs from "@/components/PageTabs";
import TypeDefensePanel from "@/components/TypeDefensePanel";
import MoveCoveragePanel from "@/components/MoveCoveragePanel";
import EffectiveStatsPanel from "@/components/EffectiveStatsPanel";

/**
 * Builder-scoped analysis page for a single configured monster slot.
 *
 * The slot index in the URL is the source identity. The actual monster +
 * config (personality, legacy type, moves, talents) is read from the builder
 * store via useBuilderStore — NOT from a URL monster id. This means the page
 * always reflects the user's in-builder configuration and updates live as
 * they edit the monster on the left side.
 */
export default function MonsterAnalysisPage() {
  const { slot: slotParam } = useParams();
  const { t } = useI18n();
  const slots = useBuilderStore((s) => s.slots);

  const slotIdx = Number(slotParam);
  const validSlot =
    Number.isInteger(slotIdx) && slotIdx >= 0 && slotIdx < slots.length;
  const slot = validSlot ? slots[slotIdx] : null;
  const monsterId = slot?.monster_id ?? 0;

  // Fetch monster detail with the SAME query key the inspector uses, so the
  // cache is shared (no extra network call when navigating from /build).
  const monsterQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(monsterId),
    queryFn: () => endpoints.monsterById(monsterId).then((r) => r.data),
    enabled: !!monsterId,
  });

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

  const detail = monsterQ.data;

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
      <TypeDefensePanel monster={detail} />
      <MoveCoveragePanel
        moveIds={[slot?.move1_id, slot?.move2_id, slot?.move3_id, slot?.move4_id]}
      />
      <EffectiveStatsPanel
        monster={detail}
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
          <MonsterInspector activeIdx={slotIdx} />
        </div>
        <div>
          <PageTabs tabs={tabs} />
        </div>
      </div>
    </div>
  );
}
