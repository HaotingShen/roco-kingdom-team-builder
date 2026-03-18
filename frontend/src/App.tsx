import { Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";
import AppShell from "./components/AppShell";

export default function App() {
  const location = useLocation();

  // Scroll to top on navigation (skip if dex scroll restoration is pending)
  useEffect(() => {
    if (sessionStorage.getItem("dex_monster_scroll")) return;
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}