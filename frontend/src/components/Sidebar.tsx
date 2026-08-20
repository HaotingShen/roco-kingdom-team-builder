import { useState } from "react";
import { NavLink } from "react-router-dom";
import { useI18n } from "@/i18n";
import { useLocalizedPath } from "@/lib/locale";
import { logoUrl } from "@/lib/images";
import { useAnnouncementUnread } from "@/hooks/useAnnouncementUnread";

const link = "block px-4 py-2 rounded hover:bg-zinc-100";
const active = "bg-zinc-200 font-medium";

function BrandLockup() {
  const { t } = useI18n();
  const localized = useLocalizedPath();
  return (
    <NavLink
      to={localized("/")}
      className="group w-full flex items-center justify-center gap-2 outline-none
                 focus-visible:ring-2 focus-visible:ring-zinc-400 rounded"
      aria-label={t("sidebar.siteName")}
      title={t("sidebar.siteName")}
    >
      <img
        src={logoUrl}
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
  const localized = useLocalizedPath();
  const hasUnread = useAnnouncementUnread();
  const [adDismissed, setAdDismissed] = useState(false);
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
        <NavLink to={localized("/")} end className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.build")}
        </NavLink>
        <NavLink to={localized("/dex")} className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.dex")}
        </NavLink>
        {!import.meta.env.VITE_HIDE_AUTH && (
          <NavLink to={localized("/teams")} className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
            {t("sidebar.teams")}
          </NavLink>
        )}
        <NavLink to={localized("/feedback")} className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          {t("sidebar.feedback")}
        </NavLink>
        <NavLink to={localized("/announcements")} className={({ isActive }) => `${link} ${isActive ? active : ""}`}>
          <span className="flex items-center justify-between">
            {t("sidebar.whatsNew")}
            {hasUnread && (
              <span className="w-2 h-2 bg-red-500 rounded-full ring-2 ring-white shrink-0" />
            )}
          </span>
        </NavLink>
      </nav>

      {/* Ad banner — hidden in TapTap build */}
      {!adDismissed && !import.meta.env.VITE_HIDE_ADS && (
        <div className="mt-auto p-3 relative">
          <button
            onClick={() => setAdDismissed(true)}
            className="absolute top-1 right-1 z-10 w-5 h-5 flex items-center justify-center rounded-full bg-zinc-200 hover:bg-zinc-300 text-zinc-500 hover:text-zinc-700 text-xs leading-none cursor-pointer"
            aria-label="Close ad"
          >
            ×
          </button>
          <a
            href="https://www.pzds.com/goodsList/3000/6/headerSearch"
            target="_blank"
            rel="noopener noreferrer"
          >
            <img
              src={`${(import.meta.env.VITE_ASSET_BASE_URL ?? "").replace(/\/$/, "")}/ad-images/pc.jpg`}
              alt="广告"
              className="w-full rounded"
              style={{ filter: "saturate(0.5)" }}
            />
          </a>
        </div>
      )}

    </aside>
  );
}