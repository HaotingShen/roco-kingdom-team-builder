import { NavLink } from "react-router-dom";
import { useI18n } from "@/i18n";

const link = "block px-4 py-2 rounded hover:bg-zinc-100";
const active = "bg-zinc-200 font-medium";

function BrandLockup() {
  const { t } = useI18n();
  return (
    <NavLink
      to="/build"
      className="group w-full flex items-center justify-center gap-2 outline-none
                 focus-visible:ring-2 focus-visible:ring-zinc-400 rounded"
      aria-label={t("sidebar.siteName")}
      title={t("sidebar.siteName")}
    >
      <img
        src="/logo.png"
        alt=""
        width={32}
        height={32}
        loading="eager"
        decoding="async"
        draggable="false"
        className="rounded-md ring-1 ring-zinc-200 bg-white shadow-sm transition"
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
      />
      <span
        className="font-semibold tracking-wide text-zinc-900 leading-tight whitespace-normal break-words"
      >
        {t("sidebar.siteName")}
      </span>
    </NavLink>
  );
}

export default function Sidebar() {
  const { t } = useI18n();
  return (
    <aside
      className="fixed left-0 top-0 h-full border-r border-zinc-200 bg-white"
      style={{ width: "var(--sidebar-w)" }}
    >
      {/* Brand area */}
      <div className="min-h-14 px-4 py-2 flex items-center border-b">
        <BrandLockup />
      </div>

      <nav className="p-3 space-y-1">
        <NavLink to="/build" className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.build")}
        </NavLink>
        <NavLink to="/dex" className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.dex")}
        </NavLink>
        <NavLink to="/teams" className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.teams")}
        </NavLink>
      </nav>
    </aside>
  );
}