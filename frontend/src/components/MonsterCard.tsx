import { useQuery, useQueries } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import type { MonsterLiteOut, PersonalityOut, TypeOut, MoveOut, TalentUpsert } from "@/types";
import { pickName, pickFormName, useI18n } from "@/i18n";
import { useMemo } from "react";
import { typeIconUrl } from "@/lib/images";
import { MonsterImage } from "./MonsterImage";
import { QUERY_KEYS } from "@/lib/constants";

/* ---------- helpers ---------- */

function typeNameRaw(t: any): string | undefined {
  return t && typeof t === "object" ? t.name : t;
}

function TypeBadge({ type, label }: { type: any; label: string }) {
  const src = typeIconUrl(typeNameRaw(type), 60);
  return (
    <span className="inline-flex items-center gap-1 rounded bg-zinc-100 px-2 py-1 text-xs">
      {src ? (
        <img
          src={src}
          alt=""
          width={20}
          height={20}
          className="inline-block"
          onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
        />
      ) : null}
      {label}
    </span>
  );
}

function useMoveMap(ids: Array<number | 0 | undefined>) {
  const uniq = useMemo(
    () => Array.from(new Set(ids.filter((x): x is number => !!x && x > 0))),
    [ids]
  );
  const results = useQueries({
    queries: uniq.map((id) => ({
      queryKey: QUERY_KEYS.MOVE_DETAIL(id),
      queryFn: () => endpoints.moveById(id).then((r) => r.data as MoveOut),
      enabled: !!id,
    })),
  });
  return useMemo(() => {
    const m = new Map<number, MoveOut>();
    results.forEach((r, i) => {
      const data = r.data;
      if (data) m.set(uniq[i]!, data);
    });
    return m;
  }, [results, uniq]);
}

/* ---------- component ---------- */

type Props = {
  monsterId?: number;
  personalityId?: number | null;
  legacyTypeId?: number | null;
  moveIds?: Array<number | 0 | undefined>;
  talent?: TalentUpsert | null;
  onClick?: () => void;
  onDelete?: () => void;
  imgSize?: 180 | 270 | 360;
};

export default function MonsterCard({
  monsterId,
  personalityId,
  legacyTypeId,
  moveIds = [],
  talent = null,
  onClick,
  onDelete,
  imgSize = 360,
}: Props) {
  const { lang, t } = useI18n();

  const monsterQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(monsterId ?? 0),
    queryFn: () => endpoints.monsterById(monsterId!).then((r) => r.data as MonsterLiteOut),
    enabled: !!monsterId,
  });
  const monster = monsterQ.data;
  const formLabel = pickFormName(monster, lang);

  // Image fallbacks: CN -> EN -> ID -> placeholder
  const persQ = useQuery({
    queryKey: QUERY_KEYS.PERSONALITIES,
    queryFn: () => endpoints.personalities().then((r) => r.data as PersonalityOut[]),
    enabled: true,
  });
  const typeQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    enabled: true,
  });

  const persName =
    personalityId && persQ.data ? pickName(persQ.data.find((p) => p.id === personalityId), lang) : "";

  const legacyObj = legacyTypeId && typeQ.data ? typeQ.data.find((t) => t.id === legacyTypeId) : null;
  const legacyName = legacyObj ? pickName(legacyObj, lang) : "";

  const moveMap = useMoveMap(moveIds);
  const mainTypeLabel = monster?.main_type ? pickName(monster.main_type as any, lang) : "";
  const subTypeLabel = monster?.sub_type ? pickName(monster.sub_type as any, lang) : "";

  const talentChips = useMemo(() => {
    if (!talent) return [];
    const labels: Record<keyof TalentUpsert, string> = {
      hp_boost: t("labels.hp"),
      phy_atk_boost: t("labels.phyAtk"),
      mag_atk_boost: t("labels.magAtk"),
      phy_def_boost: t("labels.phyDef"),
      mag_def_boost: t("labels.magDef"),
      spd_boost: t("labels.spd"),
    };
    const order: (keyof TalentUpsert)[] = [
      "hp_boost",
      "phy_atk_boost",
      "mag_atk_boost",
      "phy_def_boost",
      "mag_def_boost",
      "spd_boost",
    ];
    return order
      .filter((k) => (talent[k] ?? 0) > 0)
      .map((k) => ({ key: k, label: labels[k], val: talent[k] as number }));
  }, [talent, t]);

  // Keyboard support to activate on Enter/Space
  const onKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (e) => {
    if (!onClick) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : -1}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className="relative w-full rounded border border-zinc-200 bg-white hover:border-zinc-300 transition p-3 text-left"
    >
      {/* single delete control */}
      {onDelete && monster ? (
        <button
          className="absolute top-2 right-2 text-[11px] rounded border px-2 py-0.5 bg-red-50 text-red-700 hover:bg-red-100
             border border-red-200 focus:outline-none focus:ring-2 focus:ring-red-300 focus:ring-offset-1
             transition-colors cursor-pointer"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          title={t("builder.deleteMonster")}
          aria-label={t("builder.deleteMonster")}
        >
          {t("builder.deleteMonster")}
        </button>
      ) : null}

      {monster ? (
        <div className="flex gap-3">
          {/* avatar */}
          <div className="shrink-0">
            <MonsterImage
              monster={monster}
              size={imgSize}
              alt=""
              width={60}
              height={60}
              className="rounded-md object-contain"
            />
          </div>

          <div className="min-w-0 flex-1">
            {/* name + form on separate lines */}
            <div className="font-medium truncate" title={pickName(monster as any, lang)}>
              {pickName(monster as any, lang)}
            </div>
            {formLabel ? (
              <div className="text-xs text-zinc-500 truncate" title={formLabel}>
                {formLabel}
              </div>
            ) : null}

            {/* type chips */}
            <div className="mt-1 flex flex-wrap gap-1">
              {monster?.main_type && <TypeBadge type={monster.main_type} label={mainTypeLabel} />}
              {monster?.sub_type && <TypeBadge type={monster.sub_type} label={subTypeLabel} />}
            </div>

            {/* personality + legacy */}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded bg-zinc-50 px-2 py-1 text-[11px] text-zinc-600">
                <span className="whitespace-nowrap">{t("builder.personality")}:</span>
                <span className={persName ? "text-zinc-700" : "text-zinc-500"}>{persName || "—"}</span>
              </span>

              <span className="inline-flex items-center gap-1 rounded bg-zinc-50 px-2 py-1 text-[11px] text-zinc-600">
                <span className="whitespace-nowrap">{t("labels.legacy")}:</span>
                <span className="inline-flex items-center gap-0.5">
                  {legacyObj && typeIconUrl(typeNameRaw(legacyObj)) ? (
                    <img
                      src={typeIconUrl(typeNameRaw(legacyObj))!}
                      alt=""
                      width={18}
                      height={18}
                      onError={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")}
                    />
                  ) : null}
                  <span className={legacyName ? "text-zinc-700" : "text-zinc-500"}>{legacyName || "—"}</span>
                </span>
              </span>
            </div>

            {/* talents as chips (hide zeros) */}
            {talentChips.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {talentChips.map((tc) => (
                  <span key={tc.key} className="rounded bg-zinc-50 px-2 py-1 text-[11px] text-zinc-700">
                    {tc.label} +{tc.val}
                  </span>
                ))}
              </div>
            )}

            {/* moves as chips */}
            {moveIds.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {moveIds.map((id, idx) => {
                  if (!id) {
                    return (
                      <span key={`empty-${idx}`} className="rounded bg-zinc-50 px-2 py-1 text-[11px] text-zinc-500">
                        {t("builder.moveN", { n: idx + 1 })}: —
                      </span>
                    );
                  }
                  const move = moveMap.get(id);
                  const name = move ? pickName(move as any, lang) : "…";
                  return (
                    <span
                      key={`${id}-${idx}`}
                      className="rounded border bg-white px-2 py-1 text-[11px] text-zinc-700"
                      title={name}
                    >
                      {name}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-zinc-500">{t("builder.selectMonster")}</div>
      )}
    </div>
  );
}