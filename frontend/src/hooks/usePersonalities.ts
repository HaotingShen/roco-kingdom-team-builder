import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import type { PersonalityOut } from "@/types";

/**
 * Shared react-query hook for the /personalities list.
 *
 * The list is tiny (a couple of dozen rows), never changes at runtime, and is
 * read by multiple panels on the analysis surface. Every consumer was writing
 * the same `useQuery({ queryKey: QUERY_KEYS.PERSONALITIES, ... })` block;
 * wrapping it here keeps the query key and fetch shape in one place.
 *
 * Callers still get the full `UseQueryResult` so they can discriminate loading
 * / error states as they see fit.
 */
export function usePersonalities(): UseQueryResult<PersonalityOut[]> {
  return useQuery({
    queryKey: QUERY_KEYS.PERSONALITIES,
    queryFn: () =>
      endpoints.personalities().then((r) => r.data as PersonalityOut[]),
  });
}
