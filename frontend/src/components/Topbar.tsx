import { useNavigate, useLocation, Link } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { useI18n } from "@/i18n";
import { useBuilderStore } from "@/features/builder/builderStore";
import { useAuthStore } from "@/features/auth/authStore";
import { useMutation } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import type { TeamOut } from "@/types";
import UserMenu from "./UserMenu";

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
      <h1 className="font-medium text-zinc-800">{title}</h1>
      <div className="flex-1" />

      <div className="flex items-center gap-2">
        {isOnBuilder && (
          <>
            {/* Quick Build */}
            <button
              onClick={onQuickBuildClick}
              className="h-9 px-3 rounded-lg border border-zinc-200 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors"
              title={t("topbar.quickBuild")}
            >
              {quickBuild.isPending ? t("topbar.quickBuilding") : t("topbar.quickBuild")}
            </button>
            {quickBuildMsg && (
              <span className="text-xs text-zinc-500 max-w-[120px] truncate">{quickBuildMsg}</span>
            )}

            {/* Reset */}
            <button
              onClick={onResetClick}
              className="h-9 px-3 rounded-lg border border-zinc-200 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors"
              title={t("topbar.reset")}
            >
              {t("topbar.reset") ?? "Reset"}
            </button>
          </>
        )}

        <button
          onClick={() => setLang(lang === "en" ? "zh" : "en")}
          className="h-9 px-3 rounded-lg border border-zinc-200 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors"
          title={t("topbar.toggleLanguage")}
        >
          {lang === "en" ? t("topbar.lang_en_zh") : t("topbar.lang_zh_en")}
        </button>

        {/* Admin Link (visible to admins only) */}
        {user?.is_admin && (
          <Link
            to="/admin"
            className="h-9 px-3 rounded-lg border border-purple-200 bg-purple-50 text-sm font-medium text-purple-700 hover:bg-purple-100 flex items-center transition-colors"
            title={t("topbar.admin")}
          >
            {t("topbar.admin") ?? "Admin"}
          </Link>
        )}

        {/* User Menu */}
        <UserMenu />
      </div>
    </header>
  );
}