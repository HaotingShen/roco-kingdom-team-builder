import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { endpoints } from "@/lib/api";
import type { MonsterLiteOut } from "@/types";
import useDebounce from "@/hooks/useDebounce";
import { useI18n, pickName, useTypeIndex, localizeTypeName, pickFormName } from "@/i18n";
import { monsterImageUrlByCN, monsterImageUrlByEN, monsterImageUrlById } from "@/lib/images";

export default function MonsterPicker({
  onPick,
}: {
  onPick: (m: MonsterLiteOut) => void;
}) {
  const [q, setQ] = useState("");
  const dq = useDebounce(q, 250);
  const { lang, t } = useI18n();
  const { index: typeIndex } = useTypeIndex();

  const list = useQuery({
    queryKey: ["monsters", dq],
    queryFn: () => endpoints.monsters({ name: dq }).then((r) => r.data),
  });

  const items: MonsterLiteOut[] = list.data?.items ?? list.data ?? [];

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{t("builder.pickAMonster")}</div>

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("builder.searchMonsters")}
        className="w-full h-9 border rounded px-3"
      />

      <div className="grid grid-cols-2 gap-2 max-h-[60vh] overflow-auto">
        {items.map((m) => {
          // robust type extraction (string or object)
          const mainTypeRaw =
            typeof (m as any).main_type === "string"
              ? (m as any).main_type
              : (m as any).main_type?.name;
          const subTypeRaw =
            typeof (m as any).sub_type === "string"
              ? (m as any).sub_type
              : (m as any).sub_type?.name;

          const mainType = localizeTypeName(mainTypeRaw, lang, typeIndex);
          const subType = localizeTypeName(subTypeRaw, lang, typeIndex);
          const formLabel = pickFormName(m as any, lang);
          const displayName = pickName(m as any, lang) || (m as any).name;

          // image fallback chain: CN -> EN -> ID -> placeholder
          const imgChain = [
            monsterImageUrlByCN(m, 180),
            monsterImageUrlByEN(m, 180),
            monsterImageUrlById(m, 180),
            "/monsters/placeholder.png",
          ].filter(Boolean) as string[];

          return (
            <button
              key={(m as any).id}
              onClick={() => onPick(m)}
              className="p-2 border rounded hover:bg-zinc-50 text-left flex items-center justify-between gap-2"
            >
              {/* left: text block */}
              <div className="min-w-0 flex-1">
                <div className="font-medium truncate" title={displayName}>
                  {displayName}
                </div>
                {formLabel ? (
                  <div
                    className="text-xs text-zinc-500 truncate"
                    title={formLabel}
                  >
                    {formLabel}
                  </div>
                ) : null}
                <div className="mt-1 text-xs text-zinc-600 truncate">
                  {mainType}
                  {subType ? ` / ${subType}` : ""}
                  {(m as any).is_leader_form
                    ? lang === "zh"
                      ? " • 首领"
                      : " • Leader"
                    : ""}
                </div>
              </div>

              {/* right: thumbnail */}
              <div className="shrink-0">
                {imgChain.length ? (
                  <img
                    src={imgChain[0]!}
                    loading="lazy"
                    alt=""
                    width={40}
                    height={40}
                    className="h-12 w-12 rounded object-contain"
                    data-fallback-step={0}
                    onError={(e) => {
                      const img = e.currentTarget as HTMLImageElement;
                      const step = Number(img.dataset.fallbackStep || "0");
                      const next = step + 1;
                      if (next < imgChain.length) {
                        img.dataset.fallbackStep = String(next);
                        img.src = imgChain[next]!;
                      } else if (img.src !== "/monsters/placeholder.png") {
                        img.src = "/monsters/placeholder.png";
                      }
                    }}
                  />
                ) : null}
              </div>
            </button>
          );
        })}
      </div>

      {list.isLoading && (
        <div className="text-xs text-zinc-500">
          {t("common.loading")}
        </div>
      )}
    </div>
  );
}