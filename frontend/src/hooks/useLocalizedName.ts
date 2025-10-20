import { useMemo } from "react";
import { useI18n, pickName, pickDesc } from "@/i18n";
import type { Named } from "@/types";

/**
 * Hook to get localized name for an entity
 */
export function useLocalizedName(item: Named | null | undefined): string {
  const { lang } = useI18n();
  return useMemo(() => pickName(item, lang), [item, lang]);
}

/**
 * Hook to get localized description for an entity
 */
export function useLocalizedDesc(item: Named | null | undefined): string {
  const { lang } = useI18n();
  return useMemo(() => pickDesc(item, lang), [item, lang]);
}

/**
 * Hook to get both name and description
 */
export function useLocalizedContent(item: Named | null | undefined) {
  const { lang } = useI18n();
  return useMemo(
    () => ({
      name: pickName(item, lang),
      description: pickDesc(item, lang),
    }),
    [item, lang]
  );
}
