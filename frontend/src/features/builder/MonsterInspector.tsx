import { useQuery, useQueries } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName } from "@/i18n";
import MonsterPicker from "./MonsterPicker";
import { useBuilderStore } from "./builderStore";
import type { ID, MoveOut, PersonalityOut, TypeOut, UserMonsterCreate } from "@/types";
import { useMemo, useEffect } from "react";
import CustomSelect from "@/components/CustomSelect";
import { useNavigate } from "react-router-dom";
import { typeIconUrl } from "@/lib/images";
import { formatRowEffects, formatSentenceEffects } from "@/lib/personality";
import { QUERY_KEYS } from "@/lib/constants";

// ---------- helpers ----------
function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="text-[11px] px-3 py-2 rounded-lg border border-amber-300 bg-amber-50 text-amber-800 shadow-sm flex items-start gap-2"
    >
      <span className="inline-flex items-center justify-center w-3 h-3 rounded-full bg-amber-400 text-white text-[9px] font-bold shrink-0 mt-[3px]">!</span>
      <div className="flex-1">{children}</div>
    </div>
  );
}

function useMonsterDetail(monsterId: ID | 0) {
  return useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(monsterId),
    queryFn: () => endpoints.monsterById(monsterId!).then((r) => r.data),
    enabled: !!monsterId,
  });
}

// Build maps using raw IDs (no network fetch needed)
function extractLegacyInfo(detail: any): {
  byType: Map<number, number>;
  idSet: Set<number>;
} {
  const byType = new Map<number, number>();
  const idSet = new Set<number>();
  if (!detail) return { byType, idSet };

  if (detail.legacy_moves_by_type) {
    for (const [k, v] of Object.entries(detail.legacy_moves_by_type)) {
      const typeId = Number(k);
      const moveId =
        typeof v === "number"
          ? v
          : typeof (v as any)?.id === "number"
          ? (v as any).id
          : typeof (v as any)?.move_id === "number"
          ? (v as any).move_id
          : undefined;
      if (typeId && typeof moveId === "number") {
        byType.set(typeId, moveId);
        idSet.add(moveId);
      }
    }
  } else if (Array.isArray(detail?.legacy_moves)) {
    for (const row of detail.legacy_moves) {
      const typeId = Number(row?.type_id ?? row?.type?.id);
      const moveId = Number(row?.move_id ?? row?.move?.id);
      if (typeId && moveId) {
        byType.set(typeId, moveId);
        idSet.add(moveId);
      }
    }
  }

  return { byType, idSet };
}

function useLegacyMap(detail: any) {
  const outPairs: Array<{ type_id: number; move_id: number }> = [];
  if (detail) {
    if (detail.legacy_moves_by_type) {
      for (const [k, v] of Object.entries(detail.legacy_moves_by_type)) {
        const typeId = Number(k);
        const moveId =
          typeof v === "number"
            ? v
            : typeof (v as any)?.id === "number"
            ? (v as any).id
            : typeof (v as any)?.move_id === "number"
            ? (v as any).move_id
            : 0;
        if (typeId && moveId) outPairs.push({ type_id: typeId, move_id: moveId });
      }
    } else if (Array.isArray(detail?.legacy_moves)) {
      for (const row of detail.legacy_moves) {
        const typeId = Number(row?.type_id ?? row?.type?.id ?? 0);
        const moveId = Number(row?.move_id ?? row?.move?.id ?? 0);
        if (typeId && moveId) outPairs.push({ type_id: typeId, move_id: moveId });
      }
    }
  }

  const moveIds = Array.from(new Set(outPairs.map((x) => x.move_id)));
  const moveIdToTypeId = new Map<number, number>();
  outPairs.forEach(({ type_id, move_id }) => moveIdToTypeId.set(move_id, type_id));

  const results = useQueries({
    queries: moveIds.map((id) => ({
      queryKey: QUERY_KEYS.MOVE_DETAIL(id),
      queryFn: () => endpoints.moveById(id).then((r) => r.data as MoveOut),
      enabled: !!id,
    })),
  });

  const loading = results.some((r) => r.isLoading);

  const legacyMap = new Map<number, MoveOut>();
  results.forEach((r, idx) => {
    const move = r.data;
    if (!move) return;
    const moveId = moveIds[idx]!;
    const typeId = moveIdToTypeId.get(moveId);
    if (typeof typeId === "number") legacyMap.set(typeId, move);
  });

  return { legacyMap, loading };
}

// Helper to extract type name from type object or string
function getTypeName(type: any): string | undefined {
  return typeof type === "string" ? type : type?.name;
}

const moveKeys = {
  1: "move1_id",
  2: "move2_id",
  3: "move3_id",
  4: "move4_id",
} as const;
type MoveKey = typeof moveKeys[keyof typeof moveKeys];

function MovesSection({
  slot,
  detail,
  legacyTypeId,
  onChange,
}: {
  slot: UserMonsterCreate;
  detail: any;
  legacyTypeId: ID;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
}) {
  const { lang, t } = useI18n();
  const movePool: MoveOut[] = detail?.move_pool ?? [];

  const { legacyMap, loading: legacyLoading } = useLegacyMap(detail);

  const allowedLegacy = legacyTypeId ? legacyMap.get(legacyTypeId) : undefined;
  const allLegacyMoves = useMemo(
    () => Array.from(legacyMap.values()),
    [legacyMap]
  );

  const candidates: { move: MoveOut; isLegacy: boolean }[] = useMemo(() => {
    const base = movePool.map((m) => ({ move: m, isLegacy: false }));
    if (legacyTypeId) {
      if (allowedLegacy) base.unshift({ move: allowedLegacy, isLegacy: true });
    } else {
      if (!legacyLoading) {
        base.unshift(
          ...allLegacyMoves.map((m) => ({ move: m, isLegacy: true }))
        );
      }
    }
    return base;
  }, [movePool, allowedLegacy, legacyTypeId, allLegacyMoves, legacyLoading]);

  const legacyIdSet = useMemo(
    () => new Set(allLegacyMoves.map((m) => m.id)),
    [allLegacyMoves]
  );
  const selectedIds = [
    slot.move1_id,
    slot.move2_id,
    slot.move3_id,
    slot.move4_id,
  ].filter(Boolean) as ID[];

  const setNth = (n: 1 | 2 | 3 | 4, id: ID) => {
    const key: MoveKey = moveKeys[n];
    onChange({ [key]: id } as any);
  };

  const canPick = (n: 1 | 2 | 3 | 4, move: MoveOut, isLegacy: boolean) => {
    const currentId = (slot as any)[moveKeys[n]] as ID;
    if (move.id !== currentId && selectedIds.includes(move.id)) return false;
    if (!isLegacy) return true;
    const selectedLegacyIds = selectedIds.filter((id) => legacyIdSet.has(id));
    const alreadyHasLegacy =
      selectedLegacyIds.length > 0 &&
      !(selectedLegacyIds.length === 1 && selectedLegacyIds[0] === currentId);
    if (alreadyHasLegacy) return false;
    return true;
  };

  const onPick = (n: 1 | 2 | 3 | 4, opt: string) => {
    const id = Number(opt || 0) as ID;
    if (!id) {
      setNth(n, 0 as ID);
      return;
    }
    const found = candidates.find((c) => c.move.id === id);
    if (!found) {
      setNth(n, id);
      return;
    }

    if (found.isLegacy) {
      if (!legacyTypeId) {
        let newTypeId: ID | undefined;
        for (const [tId, m] of legacyMap.entries()) {
          if (m.id === id) {
            newTypeId = Number(tId) as ID;
            break;
          }
        }
        if (newTypeId) {
          onChange({ legacy_type_id: newTypeId, [moveKeys[n]]: id } as any);
          return;
        }
      }
    }

    setNth(n, id);
  };

  return (
    <div className="space-y-2">
      {[1, 2, 3, 4].map((n) => {
        const currentId = (slot as any)[moveKeys[n as 1 | 2 | 3 | 4]] as ID;

        const opts = candidates.map((c) => ({
          value: c.move.id,
          label: pickName(c.move as any, lang) || c.move.name,
          rightLabel: c.isLegacy ? `[${t("labels.legacy")}]` : undefined,
          disabled: !canPick(n as 1 | 2 | 3 | 4, c.move, c.isLegacy),
          leftIconUrl: c.move?.move_type ? typeIconUrl(getTypeName(c.move.move_type), 30) : null,
        }));

        return (
          <div key={n} className="flex items-center gap-2">
            <div className="w-16 text-xs text-zinc-500">{t("builder.moveN", { n })}</div>

            <div className="flex-1 min-w-0">
              <CustomSelect
                value={currentId || null}
                options={opts}
                placeholder="—"
                onChange={(id) => onPick(n as 1|2|3|4, String(id || ""))}
                containerClassName="flex-1 min-w-0"
                buttonClassName="w-full"
              />
            </div>
          </div>
        );
      })}

      <Warn>{t("builder.legacyHint")}</Warn>
    </div>
  );
}

function PersonalitySelect({
  value,
  options,
  onChange,
  placeholder,
}: {
  value?: number | null;
  options: PersonalityOut[];
  onChange: (id: number) => void;
  placeholder?: string;
}) {
  const { lang, t } = useI18n();

  const opts = (options ?? []).map((p) => ({
    value: p.id,
    label: pickName(p as any, lang),
    rightLabel: formatRowEffects(p, t),
  }));

  return (
    <CustomSelect
      value={value ?? null}
      options={opts}
      placeholder={placeholder ?? t("common.select")}
      onChange={(id) => onChange(id)}
    />
  );
}

function PersonalitySection({
  slot,
  onChange,
}: {
  slot: UserMonsterCreate;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
}) {
  const { t } = useI18n();
  const { data } = useQuery({
    queryKey: QUERY_KEYS.PERSONALITIES,
    queryFn: () =>
      endpoints.personalities().then((r) => r.data as PersonalityOut[]),
  });

  const selected = (data ?? []).find((p) => p.id === slot.personality_id);

  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-zinc-800">{t("builder.personality")}</div>

      <PersonalitySelect
        value={slot.personality_id || null}
        options={data ?? []}
        onChange={(id) => onChange({ personality_id: id })}
      />

      {selected && (
        <div className="text-xs text-emerald-700 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 shadow-sm">
          {t("builder.effects", {
            text: formatSentenceEffects(selected, t),
          })}
        </div>
      )}
    </div>
  );
}

function LegacyTypeSection({
  slot,
  onChange,
  onLegacyChange,
  disabled,
}: {
  slot: UserMonsterCreate;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
  onLegacyChange?: (newTypeId: ID) => void;
  disabled?: boolean;
}) {
  const { lang, t } = useI18n();
  const { data } = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  const opts = (data ?? []).map(type => ({
    value: type.id,
    label: pickName(type as any, lang),
    leftIconUrl: typeIconUrl(getTypeName(type), 30),
  }));

  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-zinc-800">{t("builder.legacyType")}</div>

      <CustomSelect
        value={slot.legacy_type_id || null}
        options={opts}
        placeholder={t("common.select")}
        onChange={(v) => {
          const id = (Number(v || 0) as ID);
          onChange({ legacy_type_id: id });
          onLegacyChange?.(id);
        }}
        disabled={!!disabled}
      />
    </div>
  );
}

function TalentsSection({
  slot,
  onChange,
}: {
  slot: UserMonsterCreate;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
}) {
  const { t } = useI18n();
  const allowed = [0, 7, 8, 9, 10];

  const KEYS: (keyof UserMonsterCreate["talent"])[] = [
    "hp_boost",
    "phy_atk_boost",
    "mag_atk_boost",
    "phy_def_boost",
    "mag_def_boost",
    "spd_boost",
  ];

  const LABELS: Record<(typeof KEYS)[number], string> = {
    hp_boost: t("labels.hp"),
    phy_atk_boost: t("labels.phyAtk"),
    mag_atk_boost: t("labels.magAtk"),
    phy_def_boost: t("labels.phyDef"),
    mag_def_boost: t("labels.magDef"),
    spd_boost: t("labels.spd"),
  };

  function setTalent(k: (typeof KEYS)[number], v: number) {
    const tal = { ...(slot.talent || {}) };
    tal[k] = v;
    const boosted = KEYS.filter((k2) => (tal[k2] ?? 0) > 0).length;
    if (boosted > 3) {
      alert(t("builder.v_max3"));
      return;
    }
    onChange({ talent: tal });
  }

  return (
    <div className="space-y-3 pt-2">
      <div className="text-sm font-semibold text-zinc-800">{t("builder.talents")}</div>
      <div className="grid grid-cols-2 gap-2">
        {KEYS.map((k) => {
          const value = slot.talent?.[k] ?? 0;
          const opts = allowed.map((n) => ({ value: n, label: String(n) }));
          return (
            <div key={k} className="flex items-center gap-2">
              <div className="w-24 text-xs font-medium text-zinc-700">{LABELS[k]}</div>
              <CustomSelect
                ariaLabel={LABELS[k]}
                value={value}
                options={opts}
                onChange={(v) => setTalent(k, v)}
                buttonClassName="min-w-[64px]"
              />
            </div>
          );
        })}
      </div>

      <Warn>{t("builder.talentsHint")}</Warn>
    </div>
  );
}

// ---------- main component ----------

export default function MonsterInspector({ activeIdx }: { activeIdx: number }) {
  const { slots, setSlot } = useBuilderStore();
  const slot = slots[activeIdx];
  const nav = useNavigate();

  const monsterId = slot?.monster_id ?? 0;
  const detailQ = useMonsterDetail(monsterId);
  const detail = detailQ.data;

  const { lang, t } = useI18n();

  const onChange = (patch: Partial<UserMonsterCreate>) =>
    setSlot(activeIdx, patch as any);

  const { byType: legacyByType, idSet: legacyIdSet } = useMemo(
    () => extractLegacyInfo(detail),
    [detail]
  );

  const isLeaderForm = detail?.is_leader_form === true;
  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  const leaderTypeId: ID | null = useMemo(() => {
    if (!isLeaderForm) return null;
    const arr = typesQ.data ?? [];
    const found =
      arr.find((t) => t.name === "Leader") ||
      arr.find((t) => (t as any)?.localized?.zh?.name === "首领");
    return (found?.id as ID) ?? null;
  }, [isLeaderForm, typesQ.data]);

  useEffect(() => {
    if (isLeaderForm && leaderTypeId && slot?.legacy_type_id !== leaderTypeId) {
      onChange({ legacy_type_id: leaderTypeId });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLeaderForm, leaderTypeId]);

  const handleLegacyChange = (newTypeId: ID) => {
    const allowedMoveId = legacyByType.get(Number(newTypeId));
    const patch: Partial<UserMonsterCreate> = {};

    ([1, 2, 3, 4] as const).forEach((n) => {
      const key: MoveKey = moveKeys[n];
      const current = (slot as any)[key] as ID;
      if (
        current &&
        legacyIdSet.has(Number(current)) &&
        Number(current) !== Number(allowedMoveId ?? -1)
      ) {
        (patch as any)[key] = 0;
      }
    });

    if (Object.keys(patch).length) onChange(patch);
  };

  const { legacyMap: legacyMapMain, loading: legacyLoadingMain } =
    useLegacyMap(detail);
  const allowedLegacyMain =
    slot?.legacy_type_id && legacyMapMain.get(slot.legacy_type_id);

  const goDexForMonster = () => {
    if (!monsterId) return;
    nav(`/dex/monsters/${monsterId}`);
  };

  const inspectorTitle = useMemo(() => {
    if (!monsterId || !detail) {
      return t("builder.inspectorTitle", { n: activeIdx + 1 });
    }
    const monsterName = pickName(detail, lang) || detail.name || "";
    return `${t("builder.inspector")} — ${monsterName}`;
  }, [monsterId, detail, activeIdx, lang, t]);

  return (
    <aside className="rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white via-zinc-50 to-white shadow-md p-4 space-y-4">
      <div className="flex items-center gap-2 pb-3 border-b border-zinc-200">
        <div className="h-5 w-1 bg-gradient-to-b from-zinc-800 to-zinc-600 rounded-full" />
        <div className="font-semibold text-zinc-800">
          {inspectorTitle}
        </div>
      </div>

      {!slot ? (
        <div className="text-sm text-zinc-600">{t("builder.pickAMonster")}</div>
      ) : !slot.monster_id ? (
        <>
          <MonsterPicker onPick={(m) => onChange({ monster_id: m.id })} />
          <div className="text-[11px] text-zinc-600">{t("builder.tipAfterPick")}</div>
        </>
      ) : (
        <>
          {/* View in Dex (left) + Change Monster (right) */}
          <div className="flex items-center gap-2">
            <button
              className="flex-1 h-9 rounded-lg border-2 border-zinc-300 bg-white text-xs font-medium text-zinc-700 cursor-pointer hover:bg-zinc-50 hover:border-zinc-400 hover:shadow-sm transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
              onClick={goDexForMonster}
              title={t("builder.viewInDex")}
            >
              {t("builder.viewInDex")}
            </button>
            <button
              className="flex-1 h-9 rounded-lg border-2 border-zinc-300 bg-white text-xs font-medium text-zinc-700 cursor-pointer hover:bg-zinc-50 hover:border-zinc-400 hover:shadow-sm transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
              onClick={() =>
                onChange({ monster_id: 0, move1_id: 0, move2_id: 0, move3_id: 0, move4_id: 0 })
              }
              title={t("builder.changeMonster")}
            >
              {t("builder.changeMonster")}
            </button>
          </div>

          <PersonalitySection slot={slot} onChange={onChange} />

          <LegacyTypeSection
            slot={slot}
            onChange={onChange}
            onLegacyChange={handleLegacyChange}
            disabled={isLeaderForm}
          />

          {/* Note line: "Legacy Type grants ..." */}
          {slot.legacy_type_id ? (
            legacyLoadingMain ? (
              <div className="text-xs text-zinc-500 px-3 py-2 rounded-lg bg-zinc-50 border border-zinc-200">{t("common.loading")}</div>
            ) : allowedLegacyMain ? (
              <div className="text-xs text-emerald-700 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 shadow-sm">
                {t("builder.legacyGrants", {
                  name:
                    pickName(allowedLegacyMain as any, lang) ||
                    allowedLegacyMain.name,
                })}
              </div>
            ) : (
              <div className="text-xs text-amber-700 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 shadow-sm">
                {t("builder.legacyMissing")}
              </div>
            )
          ) : null}

          <div className="pt-2">
            <div className="text-sm font-semibold mb-2 text-zinc-800">{t("builder.moves")}</div>
            {detailQ.isLoading ? (
              <div className="text-xs text-zinc-500 px-3 py-2 rounded-lg bg-zinc-50 border border-zinc-200">{t("common.loading")}</div>
            ) : (
              <MovesSection
                slot={slot}
                detail={detail}
                legacyTypeId={slot.legacy_type_id || 0}
                onChange={onChange}
              />
            )}
          </div>

          <TalentsSection slot={slot} onChange={onChange} />
        </>
      )}
    </aside>
  );
}