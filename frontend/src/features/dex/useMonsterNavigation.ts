import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { pickName, type Lang } from "@/i18n";
import type { MonsterLiteOut, MonsterOut } from "@/types";

/**
 * Returns the previous / next monster ids for the detail-page navigation
 * arrows. Uses the same display sequence as the dex grid:
 *
 *   - Sort by COALESCE(dex_number, id) ASC, id ASC.
 *   - Collapse leader-form variants: keep only the lowest-id form per species
 *     name. Subsequent forms with the same species name are dropped from the
 *     navigation order (they share a single dex card with the representative).
 *
 * If the user lands on a non-representative leader form (e.g., via a direct
 * URL), we still anchor navigation off the representative so prev/next stay
 * in step with what the dex grid shows.
 *
 * Shares a query cache (QUERY_KEYS.MONSTERS) with the dex page, so the list
 * usually hits cache rather than triggering a fetch.
 */
export function useMonsterNavigation(
  currentMonster: MonsterOut | undefined,
  lang: Lang
) {
  const monstersQuery = useQuery<MonsterLiteOut[]>({
    queryKey: QUERY_KEYS.MONSTERS,
    queryFn: () =>
      endpoints
        .monsters()
        .then((r) => (r.data?.items ?? r.data) as MonsterLiteOut[]),
    staleTime: Infinity,
  });

  const isLoading = monstersQuery.isLoading;
  const list = monstersQuery.data ?? [];

  const { prevMonsterId, nextMonsterId } = useMemo(() => {
    if (!currentMonster || list.length === 0) {
      return { prevMonsterId: null, nextMonsterId: null };
    }

    // Sort full list by COALESCE(dex_number, id) ASC, id ASC. Matches backend.
    const sorted = [...list].sort((a, b) => {
      const ka = (a as any).dex_number ?? a.id;
      const kb = (b as any).dex_number ?? b.id;
      if (ka !== kb) return ka - kb;
      return a.id - b.id;
    });

    // Build display list: leaders collapsed by species name (lowest id wins).
    // Mirrors DexPage's displayList logic so navigation matches the grid.
    const leaderRep = new Map<string, MonsterLiteOut>();
    const displayList: MonsterLiteOut[] = [];

    for (const m of sorted) {
      if (m.is_leader_form) {
        const speciesName = pickName(m as any, lang) || m.name;
        const existing = leaderRep.get(speciesName);
        if (!existing) {
          leaderRep.set(speciesName, m);
          displayList.push(m);
        } else if (m.id < existing.id) {
          // Found a lower-id form first; swap to make it the representative.
          // (Shouldn't usually happen since we iterate sorted; defensive only.)
          const idx = displayList.indexOf(existing);
          if (idx !== -1) displayList[idx] = m;
          leaderRep.set(speciesName, m);
        }
        // Otherwise skip — this form is collapsed under the existing rep.
      } else {
        displayList.push(m);
      }
    }

    // Anchor: if the current monster is itself a non-representative leader
    // form, navigate as if we're on its representative.
    let anchorId = currentMonster.id;
    if (currentMonster.is_leader_form) {
      const speciesName = pickName(currentMonster as any, lang) || currentMonster.name;
      const rep = leaderRep.get(speciesName);
      if (rep) anchorId = rep.id;
    }

    const idx = displayList.findIndex((m) => m.id === anchorId);
    if (idx < 0) {
      return { prevMonsterId: null, nextMonsterId: null };
    }

    const prev = idx > 0 ? displayList[idx - 1] : undefined;
    const next = idx < displayList.length - 1 ? displayList[idx + 1] : undefined;
    return {
      prevMonsterId: prev ? prev.id : null,
      nextMonsterId: next ? next.id : null,
    };
  }, [currentMonster?.id, currentMonster?.is_leader_form, list, lang]);

  return {
    prevMonsterId,
    nextMonsterId,
    isLoadingPrev: isLoading,
    isLoadingNext: isLoading,
  };
}