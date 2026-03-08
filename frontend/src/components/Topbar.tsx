import { useNavigate, useLocation, Link } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { useI18n } from "@/i18n";
import { useBuilderStore } from "@/features/builder/builderStore";
import { useAuthStore } from "@/features/auth/authStore";
import { useMutation } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import type { TeamOut } from "@/types";
import UserMenu from "./UserMenu";
import DonationModal from "./DonationModal";

export default function Topbar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { lang, setLang, t } = useI18n();
  const { user } = useAuthStore();

  const resetBuilder = useBuilderStore(s => s.reset);
  const loadFromTeam = useBuilderStore(s => s.loadFromTeam);
  const clearTeamId = useBuilderStore(s => s.clearTeamId);

  // Detect if the builder currently has any work to be overwritten
  const hasCurrentWork = useBuilderStore(s => {
    const anyFilledSlot = s.slots.some(um =>
      um.monster_id ||
      um.personality_id ||
      um.legacy_type_id ||
      um.move1_id || um.move2_id || um.move3_id || um.move4_id ||
      Object.values(um.talent || {}).some(v => (v ?? 0) > 0)
    );
    return anyFilledSlot || !!s.magic_item_id || !!(s.name?.trim()) || !!s.analysis;
  });

  const title = loc.pathname.startsWith("/dex")
    ? t("topbar.dex")
    : loc.pathname.startsWith("/teams")
    ? t("topbar.teams")
    : t("topbar.builder");

  const isOnBuilder =
    loc.pathname === "/" ||
    loc.pathname.startsWith("/build");

  const onResetClick = () => {
    const ok = window.confirm(
      t("topbar.confirmReset") ?? "Reset the builder? This clears the current team and analysis."
    );
    if (!ok) return;

    resetBuilder();

    if (!isOnBuilder) nav("/build");
  };

  const [showDonation, setShowDonation] = useState(false);

  // Brief "Loaded: {name}" message shown after Quick Build succeeds
  const [quickBuildMsg, setQuickBuildMsg] = useState<string | null>(null);
  const quickBuildMsgTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Quick Build (load a random featured team into the builder as a new unsaved draft)
  const quickBuild = useMutation<TeamOut, Error, void>({
    mutationFn: async (): Promise<TeamOut> => {
      const r = await endpoints.getFeaturedTeams();
      const items: TeamOut[] = r.data ?? [];
      if (!items.length) throw new Error("No featured teams available");
      const pick = items[Math.floor(Math.random() * items.length)]!;
      return pick;
    },
    onSuccess: (team) => {
      loadFromTeam(team);
      clearTeamId();
      if (!isOnBuilder) nav("/build");
      // Show "Loaded: {name}" for 3 seconds
      if (quickBuildMsgTimer.current) clearTimeout(quickBuildMsgTimer.current);
      const name = team.name ?? "";
      const msg = (t("topbar.quickBuildLoaded") ?? "Loaded: {name}").replace("{name}", name);
      setQuickBuildMsg(msg);
      quickBuildMsgTimer.current = setTimeout(() => setQuickBuildMsg(null), 3000);
    },
    onError: () => {
      alert(t("topbar.quickBuildFailed") ?? "Failed to load a sample team.");
    },
  });

  // Cleanup timer on unmount
  useEffect(() => () => {
    if (quickBuildMsgTimer.current) clearTimeout(quickBuildMsgTimer.current);
  }, []);

  const onQuickBuildClick = () => {
    if (hasCurrentWork) {
      const ok = window.confirm(
        t("topbar.quickBuildConfirm") ??
        "This will auto-generate a new team and replace your current team. Continue?"
      );
      if (!ok) return;
    }
    quickBuild.mutate();
  };

  return (
    <header className="h-14 border-b border-zinc-200 bg-white flex items-center gap-3 px-4 sticky top-0 z-10">
      {/* Logo — shown below 800px only (sidebar is hidden there) */}
      <Link
        to="/build"
        className="lg:hidden shrink-0"
        aria-label="Home"
      >
        <img
          src="/logo.png"
          alt=""
          width={28}
          height={28}
          className="rounded-md"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
        />
      </Link>

      {/* Page title — hidden below 800px to save space */}
      <h1 className="hidden lg:block font-medium text-zinc-800 shrink-0">{title}</h1>

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        {isOnBuilder && (
          <>
            {/* Quick Build — icon only below 800px, text on 800px+ */}
            <button
              onClick={onQuickBuildClick}
              className="sm:hidden h-9 w-9 flex items-center justify-center rounded-lg border-2 border-zinc-300 text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
              title={t("topbar.quickBuild")}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button
              onClick={onQuickBuildClick}
              className="hidden sm:inline-flex items-center h-9 px-3 rounded-lg border-2 border-zinc-300 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
              title={t("topbar.quickBuild")}
            >
              {quickBuild.isPending ? t("topbar.quickBuilding") : t("topbar.quickBuild")}
            </button>
            {quickBuildMsg && (
              <span className="hidden sm:inline text-xs text-zinc-500 max-w-[120px] truncate">{quickBuildMsg}</span>
            )}

            {/* Reset — icon only below 800px, text on 800px+ */}
            <button
              onClick={onResetClick}
              className="sm:hidden h-9 w-9 flex items-center justify-center rounded-lg border-2 border-zinc-300 text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
              title={t("topbar.reset")}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
            <button
              onClick={onResetClick}
              className="hidden sm:inline-flex items-center h-9 px-3 rounded-lg border-2 border-zinc-300 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
              title={t("topbar.reset")}
            >
              {t("topbar.reset") ?? "Reset"}
            </button>
          </>
        )}

        {/* Language toggle — compact below 800px */}
        <button
          onClick={() => setLang(lang === "en" ? "zh" : "en")}
          className="h-9 px-2 sm:px-3 rounded-lg border-2 border-zinc-300 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
          title={t("topbar.toggleLanguage")}
        >
          <span className="sm:hidden">{lang === "en" ? "中" : "EN"}</span>
          <span className="hidden sm:inline">{lang === "en" ? t("topbar.lang_en_zh") : t("topbar.lang_zh_en")}</span>
        </button>

        {/* Donate — compact below 800px */}
        <button
          onClick={() => setShowDonation(true)}
          className="h-9 px-2 sm:px-3 rounded-lg border-2 border-amber-300 bg-amber-50 text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors cursor-pointer"
          title={t("topbar.donate")}
        >
          <span className="sm:hidden">♥</span>
          <span className="hidden sm:inline">{t("topbar.donate") ?? "Donate"}</span>
        </button>

        {/* Admin Link (visible to admins only) */}
        {user?.is_admin && (
          <Link
            to="/admin"
            className="h-9 px-3 rounded-lg border-2 border-purple-300 bg-purple-50 text-sm font-medium text-purple-700 hover:bg-purple-100 flex items-center transition-colors cursor-pointer"
            title={t("topbar.admin")}
          >
            {t("topbar.admin") ?? "Admin"}
          </Link>
        )}

        {/* User Menu */}
        <UserMenu />
      </div>

      <DonationModal isOpen={showDonation} onClose={() => setShowDonation(false)} />
    </header>
  );
}
