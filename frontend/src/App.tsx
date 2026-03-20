import { Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";
import AppShell from "./components/AppShell";

export default function App() {
  const location = useLocation();

  // Scroll to top on navigation.
  // Skip only when navigating back to /dex — the tab's scroll restoration effect
  // handles restoring the saved position. For all other routes (including detail
  // pages), always scroll to top so they don't inherit the dex scroll position.
  useEffect(() => {
    const isDex = location.pathname === "/dex";
    if (isDex && (sessionStorage.getItem("dex_monster_scroll") || sessionStorage.getItem("dex_move_scroll"))) return;
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}