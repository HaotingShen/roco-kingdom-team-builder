import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { endpoints } from "@/lib/api";
import type { MonsterLiteOut } from "@/types";
import useDebounce from "@/hooks/useDebounce";
import { useI18n, pickName, useTypeIndex, localizeTypeName, pickFormName } from "@/i18n";
import { MonsterImage } from "@/components/MonsterImage";
import { QUERY_KEYS } from "@/lib/constants";

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
    queryKey: QUERY_KEYS.MONSTER_LIST({ name: dq }),
    queryFn: () => endpoints.monsters({ name: dq }).then((r) => r.data),
  });

  const items: MonsterLiteOut[] = list.data?.items ?? list.data ?? [];

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{t("builder.pickAMonster")}</div>

      <div className="relative">
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("builder.searchMonsters")}
          className="w-full h-10 rounded-lg border-2 border-zinc-300 pl-8 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:border-transparent transition-all"
        />
      </div>

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

          return (
            <button
              key={(m as any).id}
              onClick={() => onPick(m)}
              className="p-3 border-2 border-zinc-200 rounded-lg bg-white shadow-sm hover:shadow-md hover:border-zinc-300 hover:-translate-y-0.5 text-left flex items-center justify-between gap-2 cursor-pointer transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
            >
              {/* left: text block */}
              <div className="min-w-0 flex-1">
                <div className="font-semibold truncate" title={displayName}>
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
                <MonsterImage
                  monster={m}
                  size={360}
                  alt=""
                  width={50}
                  height={50}
                  className="rounded object-contain"
                  loading="lazy"
                />
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