import { useI18n, type Lang } from "@/i18n";

/**
 * Prefix an internal path with a locale.
 *
 * Examples (lang = "zh"):
 *   localizedPath("zh", "/")               → "/zh/"          (homepage keeps the
 *                                             trailing slash — it is the canonical
 *                                             form used by the sitemap, hreflang,
 *                                             and the CloudFront redirects)
 *   localizedPath("zh", "/dex")            → "/zh/dex"
 *   localizedPath("zh", "/dex/monsters/1") → "/zh/dex/monsters/1"
 *   localizedPath("zh", "/en/dex")         → "/en/dex"       (already prefixed; idempotent)
 *   localizedPath("zh", "https://…")       → passthrough (external)
 *
 * Query strings/hashes should be appended by the caller AFTER localizing the
 * path part: localized("/dex/monsters/1") + `?back=${back}`.
 */
export function localizedPath(lang: Lang, path: string): string {
  if (/^(https?:|mailto:|tel:)/.test(path)) return path;
  if (/^\/(en|zh)(\/|$)/.test(path)) return path;
  if (path === "/" || path === "") return `/${lang}/`;
  return `/${lang}${path.startsWith("/") ? "" : "/"}${path}`;
}

/**
 * Hook variant: returns a localizer bound to the active locale.
 *
 *   const localized = useLocalizedPath();
 *   <Link to={localized("/dex")}>…</Link>
 *   navigate(localized(`/dex/monsters/${id}`));
 */
export function useLocalizedPath() {
  const { lang } = useI18n();
  return (path: string) => localizedPath(lang, path);
}
