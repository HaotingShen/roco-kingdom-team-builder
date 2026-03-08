import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const BASE_URL = "https://rkteambuilder.com";

interface SeoMeta {
  title: string;
  description: string;
  /** Override the canonical path (e.g. "/" for /build which shares the builder) */
  canonicalPath?: string;
}

function setAttr(selector: string, attr: string, value: string) {
  const el = document.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

export function useSeoMeta({ title, description, canonicalPath }: SeoMeta) {
  const { pathname } = useLocation();
  const canonical = canonicalPath ?? pathname;

  useEffect(() => {
    document.title = title;
    const url = `${BASE_URL}${canonical}`;

    setAttr('meta[name="description"]', "content", description);
    setAttr('meta[property="og:title"]', "content", title);
    setAttr('meta[property="og:description"]', "content", description);
    setAttr('meta[property="og:url"]', "content", url);
    setAttr('meta[name="twitter:title"]', "content", title);
    setAttr('meta[name="twitter:description"]', "content", description);
    setAttr('link[rel="canonical"]', "href", url);
  }, [title, description, canonical]);
}
