import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import type { MonsterOut } from "@/types";

/**
 * Shared react-query hook for batch-fetching monster details by id list.
 *
 * Mirrors `useMovesByIds` in API shape and dedup/sort semantics — same
 * canonical-cache-key story. Each underlying query is keyed by the SAME
 * `QUERY_KEYS.MONSTER_DETAIL(id)` that `MonsterCard` uses internally, so
 * any consumer that pre-fetches a monster id via this hook makes the
 * subsequent MonsterCard mount a cache hit (no double network call).
 *
 * Implementation note: built on `useQueries` + `combine`. The `combine`
 * callback is what gives us a referentially stable result object across
 * renders when the underlying query data hasn't changed — without it,
 * `useQueries` would return a new array identity every render and
 * downstream `useMemo` deps would thrash.
 *
 * Input may be sparse (nulls/zeros are filtered). The cleaned list is
 * deduped and sorted ascending — both so the order is deterministic for
 * snapshot tests AND so a stable list of ids feeds the queries array.
 */
export interface UseMonstersByIdsResult {
  /** id -> hydrated MonsterOut. Missing entries = still loading or errored. */
  monsters: Map<number, MonsterOut>;
  /** Dedup/sorted list of positive ids that were actually requested. */
  ids: number[];
  isLoading: boolean;
  isError: boolean;
}

export function useMonstersByIds(
  rawIds: ReadonlyArray<number | 0 | null | undefined>,
): UseMonstersByIdsResult {
  // Normalize: drop nulls/zeros, dedupe, sort ascending. The sort is what
  // makes different input orderings produce the same query set.
  const ids = useMemo(
    () =>
      Array.from(
        new Set(
          rawIds.filter((x): x is number => typeof x === "number" && x > 0),
        ),
      ).sort((a, b) => a - b),
    [rawIds],
  );

  return useQueries({
    queries: ids.map((id) => ({
      queryKey: QUERY_KEYS.MONSTER_DETAIL(id),
      queryFn: () =>
        endpoints.monsterById(id).then((r) => r.data as MonsterOut),
      enabled: id > 0,
    })),
    combine: (results) => {
      const monsters = new Map<number, MonsterOut>();
      results.forEach((q, i) => {
        if (q.data) monsters.set(ids[i]!, q.data);
      });
      return {
        monsters,
        ids,
        isLoading: results.some((q) => q.isLoading),
        isError: results.some((q) => q.isError),
      };
    },
  });
}
