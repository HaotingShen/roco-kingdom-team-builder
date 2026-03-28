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
        className="rounded-md bg-white"
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
      className="hidden lg:flex lg:flex-col fixed left-0 top-0 h-full border-r border-zinc-200 bg-white"
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
        <NavLink to="/feedback" className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.feedback")}
        </NavLink>
      </nav>

      {/* Ad banner */}
      <div className="mt-auto p-3 pb-4">
        <a
          href="https://www.pzds.com/goodsList/3000/6/headerSearch"
          target="_blank"
          rel="noopener noreferrer"
        >
          <img
            src="/ad-images/pc.jpg"
            alt="广告"
            className="w-full rounded"
            style={{ filter: "saturate(0.5)" }}
          />
        </a>
      </div>

    </aside>
  );
}