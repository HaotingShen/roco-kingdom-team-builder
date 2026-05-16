import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { LEGACY_TYPES_ORDER } from "@/lib/constants";
import type { MoveOut, TypeOut } from "@/types";

/**
 * Extract the mapping from legacy-type-id → move-id from a hydrated monster
 * detail object. Handles both the `legacy_moves_by_type` dict shape and the
 * older `legacy_moves` array shape returned by the backend.
 */
export function extractLegacyInfo(detail: any): {
  byType: Map<number, number>;
  idSet: Set<number>;
} {
  const byType = new Map<number, number>();
  const idSet = new Set<number>();
  if (!detail) return { byType, idSet };

  if (detail.legacy_moves_by_type) {
    for (const [k, v] of Object.entries(detail.legacy_moves_by_type)) {
      const typeId = Number(k);
      const moveId =
        typeof v === "number"
          ? v
          : typeof (v as any)?.id === "number"
          ? (v as any).id
          : typeof (v as any)?.move_id === "number"
          ? (v as any).move_id
          : undefined;
      if (typeId && typeof moveId === "number") {
        byType.set(typeId, moveId);
        idSet.add(moveId);
      }
    }
  } else if (Array.isArray(detail?.legacy_moves)) {
    for (const row of detail.legacy_moves) {
      const typeId = Number(row?.type_id ?? row?.type?.id);
      const moveId = Number(row?.move_id ?? row?.move?.id);
      if (typeId && moveId) {
        byType.set(typeId, moveId);
        idSet.add(moveId);
      }
    }
  }

  return { byType, idSet };
}

/**
 * Fetch the full MoveOut objects for every legacy move the monster has,
 * returning a Map<legacy-type-id, MoveOut>. Shares the same query key as
 * `useMovesByIds` so results are cache-hit when those moves have already
 * been fetched elsewhere in the session.
 */
export function useLegacyMap(detail: any): {
  legacyMap: Map<number, MoveOut>;
  loading: boolean;
} {
  const outPairs: Array<{ type_id: number; move_id: number }> = [];
  if (detail) {
    if (detail.legacy_moves_by_type) {
      for (const [k, v] of Object.entries(detail.legacy_moves_by_type)) {
        const typeId = Number(k);
        const moveId =
          typeof v === "number"
            ? v
            : typeof (v as any)?.id === "number"
            ? (v as any).id
            : typeof (v as any)?.move_id === "number"
            ? (v as any).move_id
            : 0;
        if (typeId && moveId) outPairs.push({ type_id: typeId, move_id: moveId });
      }
    } else if (Array.isArray(detail?.legacy_moves)) {
      for (const row of detail.legacy_moves) {
        const typeId = Number(row?.type_id ?? row?.type?.id ?? 0);
        const moveId = Number(row?.move_id ?? row?.move?.id ?? 0);
        if (typeId && moveId) outPairs.push({ type_id: typeId, move_id: moveId });
      }
    }
  }

  const moveIds = Array.from(new Set(outPairs.map((x) => x.move_id)));
  const moveIdToTypeId = new Map<number, number>();
  outPairs.forEach(({ type_id, move_id }) => moveIdToTypeId.set(move_id, type_id));

  const q = useQuery({
    queryKey: ["moves-by-ids", moveIds.join(",")],
    queryFn: () =>
      endpoints
        .moves({ ids: moveIds.join(",") })
        .then((r) => (r.data?.items ?? r.data) as MoveOut[]),
    enabled: moveIds.length > 0,
  });

  const loading = q.isLoading && moveIds.length > 0;

  const legacyMap = new Map<number, MoveOut>();
  (q.data ?? []).forEach((move) => {
    const typeId = moveIdToTypeId.get(move.id);
    if (typeof typeId === "number") legacyMap.set(typeId, move);
  });

  return { legacyMap, loading };
}

/**
 * Sort legacy moves by the canonical LEGACY_TYPES_ORDER based on each
 * move's own type (not the legacy-type-id used to unlock it).
 */
export function sortLegacyMoves(
  legacyMap: Map<number, MoveOut>,
  allTypes?: TypeOut[],
): MoveOut[] {
  const typeIdToName = new Map<number, string>();
  (allTypes ?? []).forEach((t) => typeIdToName.set(t.id, t.name));

  return Array.from(legacyMap.values()).sort((a, b) => {
    const typeA = (a as any).move_type || (a as any).type;
    const typeB = (b as any).move_type || (b as any).type;
    const nameA: string = typeA?.name || typeIdToName.get(typeA?.id) || "";
    const nameB: string = typeB?.name || typeIdToName.get(typeB?.id) || "";
    const indexA = LEGACY_TYPES_ORDER.indexOf(nameA as any);
    const indexB = LEGACY_TYPES_ORDER.indexOf(nameB as any);
    return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB);
  });
}
