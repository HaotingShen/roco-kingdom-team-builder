import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import type { GameTermOut } from "@/types";
import type { Lang } from "@/i18n";

export interface ParsedGameTerm {
  key: string;
  matchName: string;
  tooltipText: string;
  fullDescription: string;
}

export function useGameTerms(lang: Lang): ParsedGameTerm[] {
  const { data } = useQuery<GameTermOut[]>({
    queryKey: QUERY_KEYS.GAME_TERMS,
    queryFn: () => endpoints.gameTerms().then((r) => r.data as GameTermOut[]),
    staleTime: Infinity,
  });

  return useMemo((): ParsedGameTerm[] => {
    if (!data) return [];
    return data
      .filter((t) => {
        const td =
          lang === "zh"
            ? (t.localized?.zh?.tooltip_description ?? t.tooltip_description)
            : t.tooltip_description;
        return !!td;
      })
      .map((t) => ({
        key: t.key,
        matchName:
          lang === "zh" ? (t.localized?.zh?.name ?? t.key) : t.key,
        tooltipText:
          lang === "zh"
            ? (t.localized?.zh?.tooltip_description ?? t.tooltip_description ?? "")
            : (t.tooltip_description ?? ""),
        fullDescription:
          lang === "zh"
            ? (t.localized?.zh?.description ?? t.description)
            : t.description,
      }))
      .sort((a, b) => b.matchName.length - a.matchName.length);
  }, [data, lang]);
}
