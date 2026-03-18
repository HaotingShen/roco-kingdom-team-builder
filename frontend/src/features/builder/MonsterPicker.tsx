import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { endpoints } from "@/lib/api";
import type { MonsterLiteOut, TypeOut } from "@/types";
import useDebounce from "@/hooks/useDebounce";
import { useI18n, pickName, useTypeIndex, localizeTypeName, pickFormName } from "@/i18n";
import { MonsterImage } from "@/components/MonsterImage";
import { QUERY_KEYS } from "@/lib/constants";
import { typeIconUrl } from "@/lib/images";

export default function MonsterPicker({
  onPick,
}: {
  onPick: (m: MonsterLiteOut) => void;
}) {
  const [q, setQ] = useState("");
  const [selectedTypeId, setSelectedTypeId] = useState<number | null>(null);
  const dq = useDebounce(q, 250);
  const { lang, t } = useI18n();
  const { index: typeIndex } = useTypeIndex();

  const types = useQuery<TypeOut[]>({
    queryKey: ["types-all"],
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
    staleTime: Infinity,
  });

  // Exclude "Leader" type from filter buttons (same logic as DexPage)
  const filterableTypes = (types.data ?? []).filter(
    (tp) => tp.name.toLowerCase() !== "leader" && (tp.localized?.zh ?? "") !== "首领"
  );

  const queryParams = {
    name: dq,
    is_leader_form: false,
    ...(selectedTypeId != null ? { type_id: selectedTypeId } : {}),
  };

  const list = useQuery({
    queryKey: QUERY_KEYS.MONSTER_LIST(queryParams),
    queryFn: () => endpoints.monsters(queryParams).then((r) => r.data),
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

      {/* Type filter buttons */}
      {filterableTypes.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {filterableTypes.map((tp) => {
            const icon = typeIconUrl(tp.name, 30);
            const label = localizeTypeName(tp.name, lang, typeIndex);
            const isActive = selectedTypeId === tp.id;
            return (
              <button
                key={tp.id}
                onClick={() => setSelectedTypeId(isActive ? null : tp.id)}
                title={label}
                className={`h-8 w-8 rounded flex items-center justify-center transition-colors cursor-pointer ${
                  isActive
                    ? "bg-zinc-800 ring-2 ring-zinc-800 ring-offset-1"
                    : "bg-zinc-100 hover:bg-zinc-200"
                }`}
              >
                {icon ? (
                  <img src={icon} alt={label} width={22} height={22} />
                ) : (
                  <span className="text-xs font-bold text-zinc-700">{tp.name.slice(0, 2)}</span>
                )}
              </button>
            );
          })}
        </div>
      )}

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
                  <div className="text-xs text-zinc-500 truncate" title={formLabel}>
                    {formLabel}
                  </div>
                ) : null}
                <div className="mt-1 text-xs text-zinc-600 truncate">
                  {mainType}
                  {subType ? ` / ${subType}` : ""}
                </div>
              </div>

              {/* right: thumbnail */}
              <div className="shrink-0 w-[50px] h-[50px] overflow-hidden rounded flex items-center justify-center">
                <MonsterImage
                  monster={m}
                  size={180}
                  alt=""
                  width={55}
                  height={55}
                  className="min-w-[55px] min-h-[55px] w-[55px] h-[55px] object-cover"
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
