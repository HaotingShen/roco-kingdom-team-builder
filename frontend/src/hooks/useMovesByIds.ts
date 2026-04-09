import { useMemo } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import type { MoveOut } from "@/types";

/**
 * Shared react-query hook for batch-fetching moves by id list.
 *
 * Consolidates the `useQuery({ queryKey: ["moves-by-ids", ids.join(",")], ... })`
 * pattern that was copy-pasted across MatchupPanel, MoveCoveragePanel, and the
 * rest of the analysis surface. Concentrating it here gives us:
 *
 *   - ONE normalization rule (dedupe + filter positive + sort ASC by id). The
 *     sort is critical: without it, `[3,1,2]` and `[1,2,3]` produce different
 *     cache keys for the same underlying fetch, defeating react-query sharing.
 *   - ONE query-key shape, typed via `QUERY_KEYS.MOVES_BY_IDS`, so a future
 *     invalidation can target all batches in one place.
 *   - A stable `ids` array we can pass downstream via `useMemo`, so consumers
 *     that depend on `ids` as a prop don't retrigger memos every render.
 *
 * Input may be sparse (nulls/zeros are filtered) — pass slot values directly
 * without pre-cleaning.
 *
 * If the cleaned list is empty, the query is disabled and `data` is undefined.
 * Callers should treat that as the "no data yet" state, same as they would
 * for a loading query.
 */
export interface UseMovesByIdsResult {
  /** react-query result for the moves fetch. */
  query: UseQueryResult<MoveOut[]>;
  /** Dedup/sorted list of positive ids that were actually requested. */
  ids: number[];
}

export function useMovesByIds(
  rawIds: ReadonlyArray<number | 0 | null | undefined>,
): UseMovesByIdsResult {
  // Normalize: drop nulls/zeros, dedupe, sort ascending. The sort is what
  // makes different input orderings share a cache entry.
  const ids = useMemo(
    () =>
      Array.from(
        new Set(
          rawIds.filter((x): x is number => typeof x === "number" && x > 0),
        ),
      ).sort((a, b) => a - b),
    [rawIds],
  );

  const joined = ids.join(",");

  const query = useQuery({
    queryKey: QUERY_KEYS.MOVES_BY_IDS(joined),
    queryFn: () =>
      endpoints
        .moves({ ids: joined })
        .then((r) => (r.data?.items ?? r.data) as MoveOut[]),
    enabled: ids.length > 0,
  });

  return { query, ids };
}
