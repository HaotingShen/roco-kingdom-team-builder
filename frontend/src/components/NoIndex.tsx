import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { setHreflang } from "@/hooks/useSeoMeta";

const BASE_URL = "https://rkteambuilder.com";

interface NoIndexProps {
  nofollow?: boolean;
}

function setAttr(selector: string, attr: string, value: string) {
  document.querySelector(selector)?.setAttribute(attr, value);
}

export default function NoIndex({ nofollow = false }: NoIndexProps) {
  const { pathname } = useLocation();

  useEffect(() => {
    const followPart = nofollow ? "nofollow" : "follow";
    setAttr('meta[name="robots"]', "content", `noindex, ${followPart}`);
  }, [nofollow]);

  // Noindex pages still emit hreflang so a shared /zh/... link resolves to the
  // proper language for humans; `noindex` keeps them out of search results.
  // (hreflang is metadata, not a content link — it doesn't conflict with
  // nofollow.) Pages that ALSO call useSeoMeta write identical values, so the
  // duplication is harmless.
  useEffect(() => {
    const pathNoLang = pathname.replace(/^\/(en|zh)(?=\/|$)/, "") || "/";
    const suffix = pathNoLang === "/" ? "/" : pathNoLang;
    setHreflang("en", `${BASE_URL}/en${suffix}`);
    setHreflang("zh", `${BASE_URL}/zh${suffix}`);
    setHreflang("x-default", `${BASE_URL}/en${suffix}`);
  }, [pathname]);

  return null;
}
