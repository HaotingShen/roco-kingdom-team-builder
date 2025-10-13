import { useQuery, useQueries } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import type { MonsterLiteOut, PersonalityOut, TypeOut, MoveOut } from "@/types";
import { pickName, pickFormName, useI18n } from "@/i18n";
import { useMemo } from "react";
import { monsterImageUrlByCN, monsterImageUrlByEN, monsterImageUrlById } from "@/lib/images";

/* ---------- helpers ---------- */

function typeNameRaw(t: any): string | undefined {
  return t && typeof t === "object" ? t.name : t;
}
function slugifyTypeName(name?: string | null): string | null {
  if (!name) return null;
  return name.toLowerCase().replace(/\s+/g, "-");
}
function typeIconUrl(type: any, size: 30 | 45 | 60 = 60): string | null {
  const slug = slugifyTypeName(typeNameRaw(type));
  return slug ? `/type-icons/${size}/${slug}.png` : null;
}

function TypeBadge({
  type,
  label,
}: {
  type: any;
  label: string;
}) {
  const src = typeIconUrl(type);
  return (
    <span className="inline-flex items-center gap-1 rounded bg-zinc-100 px-2 py-0.5 text-xs">
      {src ? (
        <img
          src={src}
          alt=""
          width={18}
          height={18}
          className="inline-block"
          onError={(e) =>
            ((e.currentTarget as HTMLImageElement).style.display = "none")
          }
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
      queryKey: ["move", id],
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
  onClick?: () => void;
  imgSize?: 180 | 270 | 360;
};

export default function MonsterCard({
  monsterId,
  personalityId,
  legacyTypeId,
  moveIds = [],
  onClick,
  imgSize = 360,
}: Props) {
  const { lang, t } = useI18n();

  const monsterQ = useQuery({
    queryKey: ["monster-lite", monsterId],
    queryFn: () =>
      endpoints.monsterById(monsterId!).then((r) => r.data as MonsterLiteOut),
    enabled: !!monsterId,
  });
  const monster = monsterQ.data;
  const formLabel = pickFormName(monster, lang);

  // Image fallbacks: CN -> EN -> ID -> placeholder
  const chain = [
    monsterImageUrlByCN(monster, imgSize),
    monsterImageUrlByEN(monster, imgSize),
    monsterImageUrlById(monster, imgSize),
    "/monsters/placeholder.png",
  ].filter(Boolean) as string[];

  const persQ = useQuery({
    queryKey: ["personalities"],
    queryFn: () =>
      endpoints.personalities().then((r) => r.data as PersonalityOut[]),
    enabled: true,
  });
  const typeQ = useQuery({
    queryKey: ["types"],
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    enabled: true,
  });

  const persName =
    personalityId && persQ.data
      ? pickName(persQ.data.find((p) => p.id === personalityId), lang)
      : "";

  const legacyObj =
    legacyTypeId && typeQ.data ? typeQ.data.find((t) => t.id === legacyTypeId) : null;
  const legacyName = legacyObj ? pickName(legacyObj, lang) : "";

  const moveMap = useMoveMap(moveIds);
  const mainTypeLabel = monster?.main_type
    ? pickName(monster.main_type as any, lang)
    : "";
  const subTypeLabel = monster?.sub_type
    ? pickName(monster.sub_type as any, lang)
    : "";

  return (
    <button
      onClick={onClick}
      className="w-full rounded border border-zinc-200 bg-white hover:border-zinc-300 transition p-3 text-left"
    >
      {monster ? (
        <div className="flex gap-3">
          {/* avatar */}
          <div className="shrink-0">
            {chain.length ? (
              <img
                src={chain[0]!}
                alt=""
                width={48}
                height={48}
                className="h-16 w-16 rounded-md object-contain"
                data-fallback-step={0}
                onError={(e) => {
                  const img = e.currentTarget as HTMLImageElement;
                  const step = Number(img.dataset.fallbackStep || "0");
                  const next = step + 1;
                  if (next < chain.length) {
                    img.dataset.fallbackStep = String(next);
                    img.src = chain[next]!;
                  } else if (img.src !== "/monsters/placeholder.png") {
                    img.src = "/monsters/placeholder.png";
                  }
                }}
              />
            ) : (
              <div className="h-12 w-12 rounded-md bg-zinc-100" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            {/* name + form on separate lines */}
            <div
              className="font-medium truncate"
              title={pickName(monster as any, lang)}
            >
              {pickName(monster as any, lang)}
            </div>
            {formLabel ? (
              <div className="text-xs text-zinc-500 truncate" title={formLabel}>
                {formLabel}
              </div>
            ) : null}

            {/* type chips */}
            <div className="mt-1 flex flex-wrap gap-1">
              {monster?.main_type && (
                <TypeBadge
                  type={monster.main_type}
                  label={mainTypeLabel}
                />
              )}
              {monster?.sub_type && (
                <TypeBadge
                  type={monster.sub_type}
                  label={subTypeLabel}
                />
              )}
            </div>

            {/* personality + legacy */}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-600">
                <span className="whitespace-nowrap">
                  {t("builder.personality")}:
                </span>
                <span className={persName ? "text-zinc-700" : "text-zinc-500"}>
                  {persName || "—"}
                </span>
              </span>

              <span className="inline-flex items-center gap-1 rounded bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-600">
                <span className="whitespace-nowrap">{t("labels.legacy")}:</span>
                {legacyObj && typeIconUrl(legacyObj) ? (
                  <img
                    src={typeIconUrl(legacyObj)!}
                    alt=""
                    width={16}
                    height={16}
                    onError={(e) =>
                      ((e.currentTarget as HTMLImageElement).style.display =
                        "none")
                    }
                  />
                ) : null}
                <span className={legacyName ? "text-zinc-700" : "text-zinc-500"}>
                  {legacyName || "—"}
                </span>
              </span>
            </div>

            {/* moves as chips */}
            {moveIds.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {moveIds.map((id, idx) => {
                  if (!id) {
                    return (
                      <span
                        key={`empty-${idx}`}
                        className="rounded bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-500"
                      >
                        {t("builder.moveN", { n: idx + 1 })}: —
                      </span>
                    );
                  }
                  const move = moveMap.get(id);
                  const name = move ? pickName(move as any, lang) : "…";
                  return (
                    <span
                      key={`${id}-${idx}`}
                      className="rounded border bg-white px-2 py-0.5 text-[11px] text-zinc-700"
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
    </button>
  );
}