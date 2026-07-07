import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { useEffect } from "react";
import AppShell from "./components/AppShell";
import { LocaleFromUrl } from "./i18n";

export default function App() {
  const { lang } = useParams<{ lang?: string }>();
  const location = useLocation();

  // Scroll to top on navigation.
  // Skip only when navigating back to /dex — the tab's scroll restoration effect
  // handles restoring the saved position. For all other routes (including detail
  // pages), always scroll to top so they don't inherit the dex scroll position.
  useEffect(() => {
    const isDex = /^\/(en|zh)\/dex$/.test(location.pathname);
    if (isDex && (sessionStorage.getItem("dex_monster_scroll") || sessionStorage.getItem("dex_move_scroll"))) return;
    window.scrollTo(0, 0);
  }, [location.pathname]);

  // Validate the locale segment: /xx/dex → /en/dex. (Real legacy paths like
  // /dex never reach here in production — CloudFront 301s them first.)
  if (lang !== "en" && lang !== "zh") {
    const restOfPath = location.pathname.replace(/^\/[^/]+/, "") || "/";
    return <Navigate to={`/en${restOfPath}${location.search}${location.hash}`} replace />;
  }

  return (
    <AppShell>
      <LocaleFromUrl />
      <Outlet />
    </AppShell>
  );
}
