import { useEffect } from "react";
import { useLocation, useParams } from "react-router-dom";

const BASE_URL = "https://rkteambuilder.com";

interface SeoMeta {
  title: string;
  description: string;
  /** Override the canonical PATH, locale-neutral (e.g. "/" — the hook prepends the locale). */
  canonicalPath?: string;
  noindex?: boolean;
  nofollow?: boolean;
}

function setAttr(selector: string, attr: string, value: string) {
  const el = document.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

/**
 * Ensure a single <link rel="alternate" hreflang="X"> tag exists with the given
 * href. Removes any existing tag with the same hreflang first (covers the
 * static defaults in index.html and previous pages' tags).
 */
export function setHreflang(hreflang: string, href: string) {
  document
    .querySelectorAll(`link[rel="alternate"][hreflang="${hreflang}"]`)
    .forEach((el) => el.remove());
  const link = document.createElement("link");
  link.setAttribute("rel", "alternate");
  link.setAttribute("hreflang", hreflang);
  link.setAttribute("href", href);
  document.head.appendChild(link);
}

export function useSeoMeta({ title, description, canonicalPath, noindex, nofollow }: SeoMeta) {
  const { pathname } = useLocation();
  const { lang: urlLang } = useParams<{ lang?: string }>();
  const lang: "en" | "zh" = urlLang === "zh" || urlLang === "en" ? urlLang : "en";

  // Strip the leading /lang segment to get the locale-neutral path.
  const pathNoLang = pathname.replace(/^\/(en|zh)(?=\/|$)/, "") || "/";
  const cp = canonicalPath ?? pathNoLang;
  // TRAILING-SLASH NORMALIZATION: the homepage canonical is "/en/" WITH the
  // slash (matching the sitemap, hreflang defaults, and CloudFront redirects,
  // which 301 bare /en → /en/). Deeper paths carry no trailing slash.
  const suffix = cp === "/" ? "/" : cp;
  const selfPath = `/${lang}${suffix}`;
  const enPath = `/en${suffix}`;
  const zhPath = `/zh${suffix}`;

  useEffect(() => {
    document.title = title;
    const selfUrl = `${BASE_URL}${selfPath}`;

    setAttr('meta[name="description"]', "content", description);
    setAttr('meta[property="og:title"]', "content", title);
    setAttr('meta[property="og:description"]', "content", description);
    setAttr('meta[property="og:url"]', "content", selfUrl);
    setAttr('meta[property="og:locale"]', "content", lang === "zh" ? "zh_CN" : "en_US");
    setAttr('meta[name="twitter:title"]', "content", title);
    setAttr('meta[name="twitter:description"]', "content", description);
    setAttr('link[rel="canonical"]', "href", selfUrl);

    // Reciprocal hreflang pair + x-default (English). Each page lists itself
    // and its sibling — required for Google to honor the pairing.
    setHreflang("en", `${BASE_URL}${enPath}`);
    setHreflang("zh", `${BASE_URL}${zhPath}`);
    setHreflang("x-default", `${BASE_URL}${enPath}`);

    const indexPart = noindex ? "noindex" : "index";
    const followPart = nofollow ? "nofollow" : "follow";
    setAttr('meta[name="robots"]', "content", `${indexPart}, ${followPart}`);
  }, [title, description, selfPath, enPath, zhPath, lang, noindex, nofollow]);
}
