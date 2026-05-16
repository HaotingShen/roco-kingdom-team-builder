import { useState, useMemo, useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickFormName } from "@/i18n";
import { QUERY_KEYS, LEGACY_TYPES_ORDER } from "@/lib/constants";
import MonsterPicker from "./MonsterPicker";
import CustomSelect from "@/components/CustomSelect";
import { MonsterImage } from "@/components/MonsterImage";
import { typeIconUrl } from "@/lib/images";
import { extractLegacyInfo, useLegacyMap, sortLegacyMoves } from "@/lib/monsterMoveOptions";
import type { ID, MoveOut, MonsterLiteOut, PersonalityOut, TypeOut, UserMonsterCreate } from "@/types";
import { formatRowEffects, formatSentenceEffects } from "@/lib/personality";

// ─── Constants ────────────────────────────────────────────────────────────────

export const EMPTY_DEFENDER_TALENT: UserMonsterCreate["talent"] = {
  hp_boost: 0,
  phy_atk_boost: 0,
  mag_atk_boost: 0,
  phy_def_boost: 0,
  mag_def_boost: 0,
  spd_boost: 0,
};

const moveKeys = {
  1: "move1_id",
  2: "move2_id",
  3: "move3_id",
  4: "move4_id",
} as const;
type MoveKey = typeof moveKeys[keyof typeof moveKeys];

function getTypeName(type: any): string | undefined {
  return typeof type === "string" ? type : type?.name;
}

// ─── Internal sub-components ──────────────────────────────────────────────────

function DefenderDexLink({
  monsterId,
  monsterName,
  detail,
}: {
  monsterId: number;
  monsterName: string;
  detail: any;
}) {
  const location = useLocation();
  const back = encodeURIComponent(location.pathname + "?tab=vsCustom");
  return (
    <Link
      to={`/dex/monsters/${monsterId}?from=analysis&back=${back}`}
      className="shrink-0 w-12 h-12 overflow-hidden rounded-lg bg-white border border-zinc-200 hover:opacity-80 transition-opacity"
    >
      <MonsterImage
        monster={detail ?? { id: monsterId }}
        size={180}
        alt={monsterName}
        width={48}
        height={48}
        className="w-full h-full object-contain"
      />
    </Link>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-semibold text-zinc-800">{children}</div>;
}

function DefenderMovesSection({
  slot,
  detail,
  onChange,
  allTypes,
}: {
  slot: UserMonsterCreate;
  detail: any;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
  allTypes: TypeOut[];
}) {
  const { lang, t } = useI18n();
  const learnableMoves: MoveOut[] = (detail as any)?.move_pool ?? [];
  const moveStones: MoveOut[] = (detail as any)?.move_stones ?? [];
  const allNonLegacyMoves = useMemo(() => [...learnableMoves, ...moveStones], [learnableMoves, moveStones]);

  const { legacyMap, loading: legacyLoading } = useLegacyMap(detail);
  const allLegacyMoves = useMemo(() => sortLegacyMoves(legacyMap, allTypes), [legacyMap, allTypes]);
  const allowedLegacy = slot.legacy_type_id ? legacyMap.get(slot.legacy_type_id) : undefined;

  const candidates: { move: MoveOut; isLegacy: boolean }[] = useMemo(() => {
    const base = allNonLegacyMoves.map((m) => ({ move: m, isLegacy: false }));
    if (slot.legacy_type_id) {
      if (allowedLegacy) base.unshift({ move: allowedLegacy, isLegacy: true });
    } else {
      if (!legacyLoading) {
        base.unshift(...allLegacyMoves.map((m) => ({ move: m, isLegacy: true })));
      }
    }
    return base;
  }, [allNonLegacyMoves, allowedLegacy, slot.legacy_type_id, allLegacyMoves, legacyLoading]);

  const legacyIdSet = useMemo(() => new Set(allLegacyMoves.map((m) => m.id)), [allLegacyMoves]);

  const selectedIds = [slot.move1_id, slot.move2_id, slot.move3_id, slot.move4_id].filter(Boolean) as ID[];

  const canPick = (n: 1 | 2 | 3 | 4, move: MoveOut, isLegacy: boolean) => {
    const currentId = (slot as any)[moveKeys[n]] as ID;
    if (move.id !== currentId && selectedIds.includes(move.id)) return false;
    if (!isLegacy) return true;
    const selectedLegacyIds = selectedIds.filter((id) => legacyIdSet.has(id));
    const alreadyHasLegacy =
      selectedLegacyIds.length > 0 &&
      !(selectedLegacyIds.length === 1 && selectedLegacyIds[0] === currentId);
    return !alreadyHasLegacy;
  };

  const onPick = (n: 1 | 2 | 3 | 4, opt: string) => {
    const id = Number(opt || 0) as ID;
    if (!id) {
      onChange({ [moveKeys[n]]: 0 } as any);
      return;
    }
    const found = candidates.find((c) => c.move.id === id);
    if (found?.isLegacy && !slot.legacy_type_id) {
      for (const [tId, m] of legacyMap.entries()) {
        if (m.id === id) {
          onChange({ legacy_type_id: Number(tId) as ID, [moveKeys[n]]: id } as any);
          return;
        }
      }
    }
    onChange({ [moveKeys[n]]: id } as any);
  };

  if (candidates.length === 0 && !legacyLoading) {
    return (
      <div className="text-xs text-amber-700 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200">
        {t("builder.noMovesWarning")}
      </div>
    );
  }

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
            <div className="w-14 text-xs text-zinc-500 shrink-0">{t("builder.moveN", { n })}</div>
            <div className="flex-1 min-w-0">
              <CustomSelect
                value={currentId || null}
                options={opts}
                placeholder="—"
                onChange={(id) => onPick(n as 1 | 2 | 3 | 4, String(id || ""))}
                containerClassName="flex-1 min-w-0"
                buttonClassName="w-full"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DefenderPersonalitySection({
  slot,
  onChange,
  personalities,
}: {
  slot: UserMonsterCreate;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
  personalities: PersonalityOut[];
}) {
  const { lang, t } = useI18n();
  const selected = personalities.find((p) => p.id === slot.personality_id) ?? null;
  const opts = personalities.map((p) => ({
    value: p.id,
    label: pickName(p as any, lang),
    rightLabel: formatRowEffects(p, t),
  }));
  return (
    <div className="space-y-1.5">
      <SectionLabel>{t("labels.personality")}</SectionLabel>
      <CustomSelect
        value={slot.personality_id || null}
        options={opts}
        placeholder={t("common.select")}
        onChange={(id) => onChange({ personality_id: id })}
      />
      {selected && (
        <div className="text-xs text-emerald-700 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 shadow-sm">
          {t("builder.effects", { text: formatSentenceEffects(selected, t) })}
        </div>
      )}
    </div>
  );
}

function DefenderLegacyTypeSection({
  slot,
  onChange,
  onLegacyChange,
  allTypes,
  detail,
}: {
  slot: UserMonsterCreate;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
  onLegacyChange: (newTypeId: ID) => void;
  allTypes: TypeOut[];
  detail: any;
}) {
  const { lang, t } = useI18n();
  const sortedTypes = useMemo(() => {
    return [...allTypes].sort((a, b) => {
      const indexA = LEGACY_TYPES_ORDER.indexOf(a.name as any);
      const indexB = LEGACY_TYPES_ORDER.indexOf(b.name as any);
      return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB);
    });
  }, [allTypes]);

  const opts = sortedTypes.map((type) => {
    const isLeaderDisabled = type.name === "Leader" && !detail?.leader_potential;
    return {
      value: type.id,
      label: pickName(type as any, lang),
      leftIconUrl: typeIconUrl(getTypeName(type), 30),
      disabled: isLeaderDisabled,
      showDisabledIndicator: isLeaderDisabled,
    };
  });

  return (
    <div className="space-y-1.5">
      <SectionLabel>{t("builder.legacyType")}</SectionLabel>
      <CustomSelect
        value={slot.legacy_type_id || null}
        options={opts}
        placeholder={t("common.select")}
        onChange={(v) => {
          const id = Number(v || 0) as ID;
          onChange({ legacy_type_id: id });
          onLegacyChange(id);
        }}
      />
    </div>
  );
}

function DefenderTalentsSection({
  slot,
  onChange,
}: {
  slot: UserMonsterCreate;
  onChange: (patch: Partial<UserMonsterCreate>) => void;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const ALLOWED = [0, 7, 8, 9, 10];
  const KEYS: (keyof UserMonsterCreate["talent"])[] = [
    "hp_boost", "phy_atk_boost", "mag_atk_boost", "phy_def_boost", "mag_def_boost", "spd_boost",
  ];
  const LABELS: Record<string, string> = {
    hp_boost: t("labels.hp"),
    phy_atk_boost: t("labels.phyAtk"),
    mag_atk_boost: t("labels.magAtk"),
    phy_def_boost: t("labels.phyDef"),
    mag_def_boost: t("labels.magDef"),
    spd_boost: t("labels.spd"),
  };

  const setTalent = (k: keyof UserMonsterCreate["talent"], v: number) => {
    const tal = { ...(slot.talent || {}) };
    tal[k] = v;
    const boosted = KEYS.filter((k2) => (tal[k2] ?? 0) > 0).length;
    if (boosted > 3) { alert(t("builder.v_max3")); return; }
    onChange({ talent: tal });
  };

  return (
    <div className="border-t border-zinc-100 pt-2">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-semibold text-zinc-500 hover:text-zinc-700 transition-colors cursor-pointer w-full text-left"
      >
        <svg
          className={`w-2.5 h-2.5 shrink-0 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
          fill="currentColor"
          viewBox="0 0 10 10"
          aria-hidden="true"
        >
          <polygon points="1,1 9,5 1,9" />
        </svg>
        {expanded ? t("analysis.vsCustomTalentsExpanded") : t("analysis.vsCustomTalentsCollapsed")}
      </button>
      {expanded && (
        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {KEYS.map((k) => {
            const value = slot.talent?.[k] ?? 0;
            const opts = ALLOWED.map((n) => ({ value: n, label: String(n) }));
            return (
              <div key={k} className="flex items-center gap-2">
                <div className="w-20 text-xs font-medium text-zinc-700">{LABELS[k]}</div>
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
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  slot: UserMonsterCreate | null;
  onChange: (slot: UserMonsterCreate | null) => void;
}

export default function CustomDefenderInspector({ slot, onChange }: Props) {
  const { lang, t } = useI18n();

  // Fetch monster detail for move pool and legacy move data
  const detailQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(slot?.monster_id ?? 0),
    queryFn: () => endpoints.monsterById(slot!.monster_id).then((r) => r.data),
    enabled: !!slot?.monster_id,
  });
  const detail = detailQ.data;

  // Personalities list (shared cache with the rest of the app)
  const personalitiesQ = useQuery({
    queryKey: QUERY_KEYS.PERSONALITIES,
    queryFn: () => endpoints.personalities().then((r) => r.data as PersonalityOut[]),
  });
  const personalities = personalitiesQ.data ?? [];

  // Types list (shared cache)
  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    staleTime: Infinity,
  });
  const allTypes = typesQ.data ?? [];

  // Legacy move helpers
  const { byType: legacyByType, idSet: legacyIdSet } = useMemo(
    () => extractLegacyInfo(detail),
    [detail],
  );
  const { legacyMap, loading: legacyLoading } = useLegacyMap(detail);
  const allowedLegacy = slot?.legacy_type_id ? legacyMap.get(slot.legacy_type_id) : undefined;

  // Auto-default personality when monster is first picked
  const autoPersonalityRef = useRef<number>(0);
  useEffect(() => {
    if (!slot || slot.personality_id !== 0) return;
    if (autoPersonalityRef.current === slot.monster_id) return;
    if (personalities.length === 0) return;
    autoPersonalityRef.current = slot.monster_id;
    onChange({ ...slot, personality_id: personalities[0]!.id });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot?.monster_id, personalities.length]);

  // Auto-default moves from the monster's move pool (fires once per monster pick)
  const autoMovesRef = useRef<number>(0);
  useEffect(() => {
    if (!slot || !detail) return;
    if (autoMovesRef.current === slot.monster_id) return;
    if (slot.move1_id !== 0) { autoMovesRef.current = slot.monster_id; return; }

    const pool: any[] = (detail as any).move_pool ?? [];
    const stones: any[] = (detail as any).move_stones ?? [];
    const all = [...pool, ...stones];
    if (all.length === 0) { autoMovesRef.current = slot.monster_id; return; }

    const ids = [0, 1, 2, 3].map((i) => {
      const m = all[i];
      if (!m) return 0;
      return typeof m === "number" ? m : (m.id ?? m.move_id ?? 0);
    }) as [number, number, number, number];

    autoMovesRef.current = slot.monster_id;
    onChange({ ...slot, move1_id: ids[0], move2_id: ids[1], move3_id: ids[2], move4_id: ids[3] });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot?.monster_id, !!detail]);

  // Clear incompatible legacy moves when legacy type changes
  const handleLegacyChange = (newTypeId: ID) => {
    const allowedMoveId = legacyByType.get(Number(newTypeId));
    const patch: Partial<UserMonsterCreate> = {};
    ([1, 2, 3, 4] as const).forEach((n) => {
      const key: MoveKey = moveKeys[n];
      const current = (slot as any)?.[key] as ID;
      if (
        current &&
        legacyIdSet.has(Number(current)) &&
        Number(current) !== Number(allowedMoveId ?? -1)
      ) {
        (patch as any)[key] = 0;
      }
    });
    if (Object.keys(patch).length) onChange({ ...slot!, ...patch });
  };

  const handleMonsterPick = (m: MonsterLiteOut) => {
    autoPersonalityRef.current = 0;
    autoMovesRef.current = 0;
    onChange({
      monster_id: m.id,
      personality_id: personalities[0]?.id ?? 0,
      legacy_type_id: 0,
      move1_id: 0,
      move2_id: 0,
      move3_id: 0,
      move4_id: 0,
      talent: EMPTY_DEFENDER_TALENT,
    });
  };

  const handleChange = (patch: Partial<UserMonsterCreate>) => {
    if (!slot) return;
    onChange({ ...slot, ...patch });
  };

  // ── No monster selected → show picker ──
  if (!slot || slot.monster_id === 0) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4 space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-zinc-100">
          <div className="h-4 w-1 bg-gradient-to-b from-zinc-700 to-zinc-500 rounded-full" />
          <span className="text-sm font-semibold text-zinc-800">{t("analysis.vsCustomTitle")}</span>
        </div>
        <p className="text-sm text-zinc-500">{t("analysis.vsCustomNoDefender")}</p>
        <MonsterPicker onPick={handleMonsterPick} />
      </div>
    );
  }

  // ── Monster selected → show config UI ──
  const monsterName = pickName(detail ?? { name: "" } as any, lang) || (detail as any)?.name || "…";
  const formName = detail ? pickFormName(detail, lang) : "";
  const mainType = (detail as any)?.main_type;
  const subType = (detail as any)?.sub_type;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-zinc-100">
        <div className="flex items-center gap-2 min-w-0">
          <div className="h-4 w-1 bg-gradient-to-b from-zinc-700 to-zinc-500 rounded-full shrink-0" />
          <span className="text-sm font-semibold text-zinc-800 truncate">{t("analysis.vsCustomTitle")}</span>
        </div>
        <button
          type="button"
          onClick={() => onChange(null)}
          className="shrink-0 text-xs font-medium text-zinc-500 border border-zinc-300 rounded-md px-2.5 py-1 hover:bg-zinc-50 hover:text-zinc-700 hover:border-zinc-400 transition-colors cursor-pointer"
        >
          {t("analysis.vsCustomChangeDefender")}
        </button>
      </div>

      {/* Monster identity bar */}
      <div className="flex items-center gap-3 p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
        <DefenderDexLink monsterId={slot.monster_id} monsterName={monsterName} detail={detail} />
        <div className="min-w-0 flex-1">
          {detailQ.isLoading ? (
            <div className="text-sm text-zinc-400">{t("common.loading")}</div>
          ) : (
            <>
              <p className="text-sm font-semibold text-zinc-900 truncate leading-tight">
                {monsterName}{formName ? ` (${formName})` : ""}
              </p>
              <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                {[mainType, subType].filter(Boolean).map((tp: any) => {
                  const icon = typeIconUrl(tp.name, 30);
                  return (
                    <span key={tp.id} className="inline-flex items-center gap-0.5 rounded-full bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600">
                      {icon && <img src={icon} alt={tp.name} className="w-4 h-4 shrink-0" />}
                      <span>{pickName(tp, lang) || tp.name}</span>
                    </span>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Config sections */}
      <DefenderPersonalitySection slot={slot} onChange={handleChange} personalities={personalities} />

      <DefenderLegacyTypeSection
        slot={slot}
        onChange={handleChange}
        onLegacyChange={handleLegacyChange}
        allTypes={allTypes}
        detail={detail}
      />

      {slot.legacy_type_id ? (
        legacyLoading ? (
          <div className="text-xs text-zinc-500 px-3 py-2 rounded-lg bg-zinc-50 border border-zinc-200">{t("common.loading")}</div>
        ) : allowedLegacy ? (
          <div className="text-xs text-emerald-700 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 shadow-sm">
            {t("builder.legacyGrants", {
              name: pickName(allowedLegacy as any, lang) || allowedLegacy.name,
            })}
          </div>
        ) : (
          <div className="text-xs text-amber-700 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 shadow-sm">
            {t("builder.legacyMissing")}
          </div>
        )
      ) : null}

      <div className="space-y-1.5">
        <SectionLabel>{t("builder.moves")}</SectionLabel>
        {detailQ.isLoading ? (
          <div className="text-xs text-zinc-400">{t("common.loading")}</div>
        ) : (
          <DefenderMovesSection slot={slot} detail={detail} onChange={handleChange} allTypes={allTypes} />
        )}
      </div>

      <DefenderTalentsSection slot={slot} onChange={handleChange} />
    </div>
  );
}
