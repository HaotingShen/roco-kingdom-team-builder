import { useState, useCallback } from "react";
import { useI18n } from "@/i18n";
import rawAnnouncements from "@/announcements.json";

// ─── Types ────────────────────────────────────────────────────────────────────
// Not exported — only used internally. Keeps react-refresh export clean.
interface Announcement {
  id: string;
  type: "info" | "warning" | "critical";
  en: string;
  zh: string;
  date: string;       // YYYY-MM-DD — start showing from this date (inclusive)
  expiresAt?: string; // YYYY-MM-DD — stop showing from this date (exclusive)
}

// resolveJsonModule: true (tsconfig.json, inherited by tsconfig.app.json) enables this.
// A JSON syntax error here fails the build — malformed announcements never reach prod.
const announcements = rawAnnouncements as Announcement[];

// ─── localStorage ─────────────────────────────────────────────────────────────
// Follows the existing rktb-* key namespace (see authStore.ts, builderStore.ts).
// Stores a JSON array of dismissed announcement IDs.
const LS_KEY = "rktb-ann-dismissed";

function loadDismissed(): string[] {
  // try/catch handles: private/incognito mode (throws), corrupted JSON, quota exceeded.
  // Graceful degradation: if read fails, treat as empty → announcements re-shown.
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    return [];
  }
}

function saveDismissed(ids: string[]): void {
  // If localStorage is unavailable or full, silently skip.
  // The announcement will re-appear on next load — acceptable degradation.
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(ids));
  } catch {
    // Intentionally ignored
  }
}

// ─── Date helper ─────────────────────────────────────────────────────────────
// Uses LOCAL calendar date (not UTC). Avoids off-by-one surprises for users in
// UTC+8 who are a calendar day ahead of the server's UTC reference.
function getTodayStr(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────
function useAnnouncements() {
  // Lazy init: read localStorage once on mount, not on every render.
  const [dismissedIds, setDismissedIds] = useState<string[]>(() => loadDismissed());

  // Empty deps is correct: setDismissedIds is a stable React state setter and
  // saveDismissed is a module-level function — neither changes between renders.
  // Idempotent: calling dismiss(id) twice never produces duplicate entries.
  const dismiss = useCallback((id: string) => {
    setDismissedIds(prev => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      saveDismissed(next);
      return next;
    });
  }, []);

  const today = getTodayStr();

  const active = announcements.filter(ann => {
    if (dismissedIds.includes(ann.id)) return false;
    if (ann.date > today) return false;                        // not yet active
    if (ann.expiresAt && ann.expiresAt <= today) return false; // already expired
    return true;
  });

  // noUncheckedIndexedAccess (tsconfig.json): .sort()[0] returns T | undefined.
  // ?? null converts undefined to null so the type is Announcement | null.
  const criticalAnn =
    [...active]
      .filter(a => a.type === "critical")
      .sort((a, b) => b.date.localeCompare(a.date))[0] ?? null;

  const bannerAnn =
    [...active]
      .filter(a => a.type !== "critical")
      .sort((a, b) => b.date.localeCompare(a.date))[0] ?? null;

  return { criticalAnn, bannerAnn, dismiss };
}

// ─── Banner (info / warning) ──────────────────────────────────────────────────
const BANNER_STYLE: Record<"info" | "warning", string> = {
  info: "bg-blue-50 border-b border-blue-200 text-blue-800",
  warning: "bg-amber-50 border-b border-amber-200 text-amber-800",
};
const BANNER_ICON: Record<"info" | "warning", string> = {
  info: "ℹ️",
  warning: "⚠️",
};
const FALLBACK_BANNER_TYPE: "info" | "warning" = "info";

function AnnouncementBanner({
  ann,
  onDismiss,
}: {
  ann: Announcement;
  onDismiss: () => void;
}) {
  const { t, lang } = useI18n();
  // ann.zh is the source of truth for Chinese text. Fall back to en if zh is empty.
  // NOTE: t() has NO runtime fallback for missing keys — both en/zh in i18n.tsx are required.
  const text = lang === "zh" && ann.zh ? ann.zh : ann.en;
  const type = ann.type === "info" || ann.type === "warning" ? ann.type : FALLBACK_BANNER_TYPE;

  // sticky top-14 = 3.5rem = 56px — exactly matches Topbar's h-14.
  // z-[9] keeps the banner below the Topbar (z-10) in the stacking context.
  // COUPLING: if Topbar height ever changes from h-14, update top-14 here too.
  return (
    <div className={`${BANNER_STYLE[type]} py-2 px-4 flex items-center gap-2 sticky top-14 z-[9] text-sm`}>
      <span className="shrink-0 leading-none" aria-hidden="true">{BANNER_ICON[type]}</span>
      <span className="flex-1 min-w-0 leading-snug">{text}</span>
      <button
        onClick={onDismiss}
        className="shrink-0 ml-1 p-1 rounded hover:bg-black/10 transition-colors cursor-pointer"
        aria-label={t("announcement.dismiss")}
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ─── Critical modal ───────────────────────────────────────────────────────────
function AnnouncementModal({
  ann,
  onDismiss,
}: {
  ann: Announcement;
  onDismiss: () => void;
}) {
  const { t, lang } = useI18n();
  const text = lang === "zh" && ann.zh ? ann.zh : ann.en;

  // Follows DonationModal.tsx pattern:
  // - fixed inset-0 z-50: full-screen overlay
  // - pb-16 lg:pb-0: clears BottomNav (h-16, z-20) on mobile
  // - No backdrop onClick: critical notices require explicit acknowledgment
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center pb-16 lg:pb-0">
      {/* Non-interactive backdrop — user must click "Got it" to dismiss */}
      <div className="absolute inset-0 bg-black/50" />

      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden">
        <div className="bg-gradient-to-r from-red-50 to-orange-50 border-b border-red-100 px-6 py-4 flex items-center gap-2">
          <span className="text-xl leading-none" aria-hidden="true">⚠️</span>
          <h2 className="text-base font-semibold text-zinc-800">
            {t("announcement.importantNotice")}
          </h2>
        </div>

        <div className="px-6 py-5">
          <p className="text-zinc-700 text-sm leading-relaxed">{text}</p>
        </div>

        <div className="px-6 pb-5 flex justify-end">
          {/* autoFocus: keyboard and screen reader users land directly on the action */}
          <button
            onClick={onDismiss}
            autoFocus
            className="px-4 py-2 rounded-lg bg-zinc-800 text-white text-sm font-medium hover:bg-zinc-700 transition-colors cursor-pointer"
          >
            {t("announcement.gotIt")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Exported system component ────────────────────────────────────────────────
// Single default export — satisfies react-refresh/only-export-components.
// Renders nothing when no active undismissed announcements exist.
export default function AnnouncementSystem() {
  const { criticalAnn, bannerAnn, dismiss } = useAnnouncements();
  // Critical modal (z-50) visually overlays the banner.
  // After modal is dismissed, the banner (if any) becomes the visible element.
  return (
    <>
      {criticalAnn && (
        <AnnouncementModal
          ann={criticalAnn}
          onDismiss={() => dismiss(criticalAnn.id)}
        />
      )}
      {bannerAnn && (
        <AnnouncementBanner
          ann={bannerAnn}
          onDismiss={() => dismiss(bannerAnn.id)}
        />
      )}
    </>
  );
}
