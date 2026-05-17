import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickFormName } from "@/i18n";
import { QUERY_KEYS } from "@/lib/constants";
import { useBuilderStore, EMPTY_TALENT } from "./builderStore";
import { useAnalysisStore } from "./analysisStore";
import { useMovesByIds } from "@/hooks/useMovesByIds";
import { usePersonalities } from "@/hooks/usePersonalities";
import NoIndex from "@/components/NoIndex";
import MonsterInspector from "./MonsterInspector";
import PageTabs from "@/components/PageTabs";
import TypeDefensePanel from "@/components/TypeDefensePanel";
import MoveCoveragePanel from "@/components/MoveCoveragePanel";
import EffectiveStatsPanel from "@/components/EffectiveStatsPanel";
import AttackerStatusSelector from "@/components/AttackerStatusSelector";
import { getAttackerStatusOptions } from "@/lib/attackerStatusOptions";
import VsFeaturedTeamsTab from "./VsFeaturedTeamsTab";
import VsCustomDefenderTab from "./VsCustomDefenderTab";
import HotLabel from "@/components/HotLabel";
import type { MonsterOut, MonsterLiteOut, TypeOut, UserMonsterCreate } from "@/types";

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
 *
 * Data-ownership model (post-refactor): this page is the single fetch site
 * for everything the analysis panels need about the ATTACKER (the configured
 * slot). Each child panel is presentational — they receive hydrated monster /
 * moves / personality via props. Concretely:
 *
 *   - `attackerMonsterQ` — one fetch, keyed by the slot's monster_id.
 *   - `useMovesByIds(attackerMoveIds)` — one batched fetch for all 4 moves.
 *   - `usePersonalities()` — shared app-wide query for the ~dozen personality
 *     rows (cached across every consumer).
 *
 * The "vs featured teams" tab then receives the attacker bundle already
 * hydrated and is responsible for hydrating any defender-side data for
 * each matchup panel it renders.
 */
// ─── Leader Form Toggle ───────────────────────────────────────────────────────

interface LeaderFormToggleProps {
  showLeaderForm: boolean;
  leaderFormName?: string;
  onToggle: (v: boolean) => void;
}

function LeaderFormToggle({ showLeaderForm, leaderFormName, onToggle }: LeaderFormToggleProps) {
  const { t } = useI18n();
  const [hintOpen, setHintOpen] = useState(false);
  const [flipDown, setFlipDown] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const hintRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!hintOpen) return;
    const close = (e: MouseEvent) => {
      if (hintRef.current && !hintRef.current.contains(e.target as Node)) setHintOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [hintOpen]);

  const openHint = useCallback(() => {
    if (btnRef.current) setFlipDown(btnRef.current.getBoundingClientRect().top < 160);
    setHintOpen((v) => !v);
  }, []);

  return (
    <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      <span className="text-xs font-semibold text-indigo-600 shrink-0 uppercase tracking-wide">
        {t("analysis.attackerFormLabel")}
      </span>
      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`text-sm cursor-pointer select-none transition-colors duration-150 ${!showLeaderForm ? "font-semibold text-zinc-800" : "text-zinc-400"}`}
          onClick={() => onToggle(false)}
        >
          {t("analysis.regularForm")}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={showLeaderForm}
          onClick={() => onToggle(!showLeaderForm)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${showLeaderForm ? "bg-indigo-500" : "bg-zinc-300"}`}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${showLeaderForm ? "translate-x-4" : "translate-x-0"}`}
          />
        </button>
        <span
          className={`text-sm cursor-pointer select-none transition-colors duration-150 ${showLeaderForm ? "font-semibold text-zinc-800" : "text-zinc-400"}`}
          onClick={() => onToggle(true)}
        >
          {t("analysis.leaderForm")}
        </span>
      </div>
      <span ref={hintRef} className="relative ml-auto shrink-0">
        <button
          ref={btnRef}
          type="button"
          onClick={openHint}
          className="w-5 h-5 rounded-full border border-indigo-300 bg-white text-indigo-400 hover:text-indigo-600 hover:border-indigo-400 text-[11px] font-bold leading-none flex items-center justify-center cursor-pointer transition-colors"
          aria-label="Help"
        >
          ?
        </button>
        {hintOpen && (
          <span onMouseDown={e => e.stopPropagation()} className={`absolute z-20 right-0 w-64 rounded-md bg-zinc-800 px-2.5 py-2 text-xs leading-snug text-white shadow-lg ${flipDown ? "top-full mt-2" : "bottom-full mb-2"}`}>
            {t("analysis.attackerFormHint")}
            <span className={`absolute right-3 border-4 border-transparent ${flipDown ? "bottom-full border-b-zinc-800" : "top-full border-t-zinc-800"}`} />
          </span>
        )}
      </span>
      <span className="text-xs text-zinc-500 leading-tight w-full sm:w-auto">
        {leaderFormName ?? t("analysis.leaderFormNote")}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export default function MonsterAnalysisPage() {
  const { slot: slotParam } = useParams();
  const [sp] = useSearchParams();
  const { t, lang } = useI18n();
  const slots = useBuilderStore((s) => s.slots);
  const slotIdx = Number(slotParam);
  const validSlot =
    Number.isInteger(slotIdx) && slotIdx >= 0 && slotIdx < slots.length;
  const slot = validSlot ? slots[slotIdx] : null;
  const monsterId = slot?.monster_id ?? 0;
  const personalityId = slot?.personality_id ?? 0;
  const talent = slot?.talent ?? EMPTY_TALENT;
  // Imperative read — no reactive subscription needed; only used for useState init.
  // useAnalysisStore.getState() avoids triggering re-renders from store writes.
  const storedSlot = useAnalysisStore.getState().slots[slotIdx];

  // URL ?tab= param wins (explicit back-from-matchup links encode the tab);
  // stored value wins over default (back from MonsterInspector's dex path, which has no ?tab=)
  const urlTab = sp.get("tab");
  const resolvedInitialTab =
    urlTab === "vsFeatured" ? "vsFeatured" :
    urlTab === "vsCustom" ? "vsCustom" :
    storedSlot?.activeTab ?? "stats";

  const [activeAnalysisTab, setActiveAnalysisTab] = useState(resolvedInitialTab);
  const [activeAttackerStatusIds, setActiveAttackerStatusIds] = useState<number[]>(storedSlot?.attackerStatusIds ?? []);
  const [customDefenderSlot, setCustomDefenderSlot] = useState<UserMonsterCreate | null>(storedSlot?.customDefender ?? null);

  // Sync all three to the store so they survive navigation — access store
  // imperatively inside each effect to avoid creating reactive subscriptions.
  useEffect(() => {
    useAnalysisStore.getState().setActiveTab(slotIdx, activeAnalysisTab);
  }, [slotIdx, activeAnalysisTab]);
  useEffect(() => {
    useAnalysisStore.getState().setCustomDefender(slotIdx, customDefenderSlot);
  }, [slotIdx, customDefenderSlot]);
  useEffect(() => {
    useAnalysisStore.getState().setAttackerStatusIds(slotIdx, activeAttackerStatusIds);
  }, [slotIdx, activeAttackerStatusIds]);

  // Leader form toggle — stored per slot so it persists across navigation and is
  // shared across all three analysis tabs (Stats, vsCustom, vsFeatured).
  const showLeaderForm = useAnalysisStore((s) => s.slots[slotIdx]?.showLeaderForm ?? false);
  const setShowLeaderForm = (v: boolean) =>
    useAnalysisStore.getState().patchSlot(slotIdx, { showLeaderForm: v });

  // ----- Attacker fetches (single source for all 3 analysis panels) -----

  const attackerMonsterQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(monsterId),
    queryFn: () =>
      endpoints.monsterById(monsterId).then((r) => r.data as MonsterOut),
    enabled: !!monsterId,
  });

  // I5: stabilize the move-id tuple so every downstream memo sees the same
  // array identity across renders when the ids haven't actually changed.
  const attackerRawMoveIds = useMemo(
    () => [slot?.move1_id, slot?.move2_id, slot?.move3_id, slot?.move4_id],
    [slot?.move1_id, slot?.move2_id, slot?.move3_id, slot?.move4_id],
  );

  const attackerMovesResult = useMovesByIds(attackerRawMoveIds);
  // useMovesByIds sorts IDs ascending for cache-key stability, so query.data
  // comes back sorted by move ID rather than slot order. Re-map to slot order
  // (move1→move2→move3→move4) so panels display moves in the same order as
  // the inspector.
  const attackerMovesData = useMemo(() => {
    const raw = attackerMovesResult.query.data;
    if (!raw) return undefined;
    const byId = new Map(raw.map((m) => m && [m.id, m] as const).filter(Boolean) as [number, typeof raw[number]][]);
    return attackerRawMoveIds
      .filter((id): id is number => typeof id === "number" && id > 0)
      .map((id) => byId.get(id))
      .filter((m): m is NonNullable<typeof m> => m != null);
  }, [attackerMovesResult.query.data, attackerRawMoveIds]);
  const attackerHasSelectedMoves = attackerMovesResult.ids.length > 0;

  const attackerStatusOptions = useMemo(
    () => getAttackerStatusOptions(attackerMovesData ?? []),
    [attackerMovesData],
  );

  // Remove status IDs that no longer correspond to moves the attacker has.
  // Guard: skip when moves haven't loaded yet — attackerStatusOptions would be []
  // and would incorrectly wipe out any stored IDs before data arrives.
  useEffect(() => {
    if (!attackerMovesData) return;
    setActiveAttackerStatusIds((ids) => {
      const validIds = new Set(attackerStatusOptions.map((status) => status.id));
      const next = ids.filter((id) => validIds.has(id));
      return next.length === ids.length ? ids : next;
    });
  }, [attackerStatusOptions, attackerMovesData]);


  const activeAttackerStatuses = useMemo(() => {
    const activeIds = new Set(activeAttackerStatusIds);
    return attackerStatusOptions.filter((status) => activeIds.has(status.id));
  }, [attackerStatusOptions, activeAttackerStatusIds]);

  const personalitiesQ = usePersonalities();
  const attackerPersonality = useMemo(
    () => personalitiesQ.data?.find((p) => p.id === personalityId) ?? null,
    [personalitiesQ.data, personalityId],
  );

  // ----- Leader form + Willpower Impact queries -----

  // Types list — needed to resolve the Leader type ID and attacker's legacy type.
  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    staleTime: Infinity,
  });

  const leaderTypeId = useMemo(
    () => typesQ.data?.find((tp) => tp.name === "Leader")?.id ?? null,
    [typesQ.data],
  );

  // Attacker's legacy type — used for Willpower Impact damage calculation.
  const attackerLegacyType = useMemo<TypeOut | null>(() => {
    if (!typesQ.data || !slot?.legacy_type_id) return null;
    return typesQ.data.find((tp) => tp.id === slot.legacy_type_id) ?? null;
  }, [typesQ.data, slot?.legacy_type_id]);

  // Willpower Impact is always relevant unless the player selected the Leader legacy type.
  const willpowerActive = attackerLegacyType !== null && attackerLegacyType?.name !== "Leader";

  const detail: MonsterOut | undefined = attackerMonsterQ.data;

  // Step 1 — find the leader form record for this exact monster form.
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

  // Resolved attacker monster: leader form when the toggle is ON and data is ready,
  // regular form otherwise. Shared across all three tabs — Stats panel (EffectiveStatsPanel
  // only; TypeDefensePanel always uses `detail`), vsCustom, and vsFeatured.
  const activeAttackerMonster: MonsterOut | undefined =
    showLeaderForm && leaderDetailQ.data ? leaderDetailQ.data : detail;

  // Reflects leader form name when the toggle is ON.
  const attackerMonsterName = useMemo(() => {
    const m = activeAttackerMonster;
    if (!m) return undefined;
    return pickName(m, lang) || m.name || undefined;
  }, [activeAttackerMonster, lang]);

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

  // Pre-compute the active leader form label string passed down to each toggle instance.
  const leaderFormActiveName = showLeaderForm && leaderDetailQ.data
    ? (() => {
        const lm = leaderDetailQ.data;
        const name = pickName(lm, lang) || lm.name;
        const form = pickFormName(lm, lang);
        return (t("analysis.leaderFormActive") ?? "Viewing: {name}").replace(
          "{name}",
          form ? `${name} (${form})` : name,
        );
      })()
    : undefined;

  // LeaderFormToggle is a proper component — each render site gets independent
  // state and refs, so the tooltip works correctly regardless of viewport size.
  const leaderToggleBlock = showLeaderToggle ? (
    <LeaderFormToggle
      showLeaderForm={showLeaderForm}
      leaderFormName={leaderFormActiveName}
      onToggle={setShowLeaderForm}
    />
  ) : null;

  // ----- Tab 1 content (stats) -----
  // Without explicit loading + error states, TypeDefensePanel falls back to
  // its "noMonsterHint" placeholder while attackerMonsterQ is in flight,
  // which is misleading right after clicking Analyze.
  const statsTabContent = attackerMonsterQ.isLoading ? (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
      <div className="text-sm text-zinc-500">{t("common.loading")}</div>
    </section>
  ) : attackerMonsterQ.isError ? (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
      <div className="text-sm text-rose-600">{t("analysis.loadFailed")}</div>
    </section>
  ) : (
    <div className="space-y-3">
      {/* TypeDefensePanel always uses the regular form — leader forms share the same typing. */}
      <TypeDefensePanel monster={detail} />
      <MoveCoveragePanel
        moves={attackerMovesData}
        movesLoading={attackerMovesResult.query.isLoading}
        movesError={attackerMovesResult.query.isError}
        hasSelectedMoves={attackerHasSelectedMoves}
        initialEffectiveMode={storedSlot?.effectiveMode}
        initialBlindMode={storedSlot?.blindMode}
        onEffectiveModeChange={(m) => useAnalysisStore.getState().patchSlot(slotIdx, { effectiveMode: m })}
        onBlindModeChange={(m) => useAnalysisStore.getState().patchSlot(slotIdx, { blindMode: m })}
      />
      <EffectiveStatsPanel
        monster={activeAttackerMonster}
        talent={talent}
        personality={attackerPersonality}
        initialCalcAtk={storedSlot?.calcAtk}
        initialCalcPower={storedSlot?.calcPower}
        onCalcChange={(atk, power) => useAnalysisStore.getState().patchSlot(slotIdx, { calcAtk: atk, calcPower: power })}
      />
    </div>
  );

  // ----- Tabs 2 & 3 content (custom defender + vs featured teams) -----
  const attackerFetching =
    !detail ||
    attackerMovesResult.query.isLoading ||
    personalitiesQ.isLoading;
  const attackerError =
    attackerMonsterQ.isError ||
    attackerMovesResult.query.isError ||
    personalitiesQ.isError;
  // Fetches finished but personality_id is 0 or resolves to nothing.
  const attackerNeedsPersonality =
    !attackerFetching && !attackerError && !attackerPersonality;
  const attackerLoaded =
    !attackerFetching && !attackerError && !!attackerPersonality;

  function attackerGuard(content: React.ReactNode): React.ReactNode {
    if (attackerError) return (
      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
        <div className="text-sm text-rose-600">{t("analysis.loadFailed")}</div>
      </section>
    );
    if (attackerFetching) return (
      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
        <div className="text-sm text-zinc-500">{t("common.loading")}</div>
      </section>
    );
    if (attackerNeedsPersonality) return (
      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
        <div className="text-sm text-zinc-500">{t("analysis.pickPersonality")}</div>
      </section>
    );
    return attackerLoaded ? content : null;
  }

  const vsCustomTabContent = attackerGuard(
    <VsCustomDefenderTab
      attackerMonster={activeAttackerMonster!}
      attackerTalent={talent}
      attackerPersonality={attackerPersonality!}
      attackerMoves={attackerMovesData ?? []}
      attackerStatuses={activeAttackerStatuses}
      attackerLegacyType={attackerLegacyType}
      willpowerActive={willpowerActive}
      leaderTypeId={leaderTypeId}
      customDefenderSlot={customDefenderSlot}
      onCustomDefenderChange={setCustomDefenderSlot}
    />,
  );

  const vsFeaturedTabContent = attackerGuard(
    <VsFeaturedTeamsTab
      attackerMonster={activeAttackerMonster!}
      attackerTalent={talent}
      attackerPersonality={attackerPersonality!}
      attackerMoves={attackerMovesData ?? []}
      attackerStatuses={activeAttackerStatuses}
      attackerLegacyType={attackerLegacyType}
      willpowerActive={willpowerActive}
    />,
  );

  const showMatchupStatus = activeAnalysisTab === "vsFeatured" || activeAnalysisTab === "vsCustom";

  const tabs = [
    { key: "stats", label: t("analysis.tabStats"), content: statsTabContent },
    { key: "vsCustom", label: <HotLabel>{t("analysis.tabVsCustom")}</HotLabel>, content: vsCustomTabContent },
    { key: "vsFeatured", label: <HotLabel>{t("analysis.tabVsFeatured")}</HotLabel>, content: vsFeaturedTabContent },
  ];

  return (
    <>
      <NoIndex nofollow />
      <div className="space-y-3">
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[340px_1fr] xl:grid-cols-[420px_1fr]">
        <div className={`space-y-3 ${showMatchupStatus ? "lg:sticky lg:top-[72px] lg:self-start lg:max-h-[calc(100vh-72px)] lg:overflow-y-auto" : ""}`}>
          <div className="flex items-center">
            <Link
              to="/build"
              className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
            >
              <span aria-hidden className="text-xl leading-none text-zinc-600 -translate-y-[1px]">←</span>
              <span className="text-zinc-700">{t("dex.backToBuilder")}</span>
            </Link>
          </div>
          {/* Desktop: leader toggle sits above the status selector and inspector */}
          <div className="hidden lg:block">{leaderToggleBlock}</div>
          {showMatchupStatus ? (
            <div className="hidden lg:block">
              <AttackerStatusSelector
                moves={attackerMovesData ?? []}
                activeStatusIds={activeAttackerStatusIds}
                onChange={setActiveAttackerStatusIds}
                monsterName={attackerMonsterName}
              />
            </div>
          ) : null}
          <MonsterInspector
            activeIdx={slotIdx}
            context="analyze"
            dexMonsterId={showLeaderForm && leaderDetailQ.data ? leaderDetailQ.data.id : undefined}
          />
          {/* Mobile matchup tabs: leader toggle below inspector, non-sticky.
              Stats tab: toggle is rendered in the right column instead (see below)
              so it can actually stick while scrolling through the stats panels. */}
          {showMatchupStatus && leaderToggleBlock && (
            <div className="lg:hidden">{leaderToggleBlock}</div>
          )}
        </div>
        <div className="min-w-0">
          {/* Mobile Stats tab: leader toggle at top of the right column so it sits in the
              same scroll area as the stats panels and can actually stick to the top. */}
          {!showMatchupStatus && leaderToggleBlock && (
            <div className="block lg:hidden sticky top-14 z-[8] mb-3">
              {leaderToggleBlock}
            </div>
          )}
          {/* Mobile-only sticky attacker status — desktop version lives in the left column */}
          {showMatchupStatus && (
            <div className="block lg:hidden sticky top-14 z-[9] mb-3">
              <AttackerStatusSelector
                moves={attackerMovesData ?? []}
                activeStatusIds={activeAttackerStatusIds}
                onChange={setActiveAttackerStatusIds}
                monsterName={attackerMonsterName}
              />
            </div>
          )}
          <PageTabs
            tabs={tabs}
            activeTab={activeAnalysisTab}
            onTabChange={setActiveAnalysisTab}
          />
        </div>
      </div>
    </div>
    </>
  );
}
