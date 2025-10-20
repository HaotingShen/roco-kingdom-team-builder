import { Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";
import AppShell from "./components/AppShell";

export default function App() {
  const location = useLocation();

  // Scroll to top on navigation
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}