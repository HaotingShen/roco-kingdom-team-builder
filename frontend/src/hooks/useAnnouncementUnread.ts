import { useState, useEffect } from "react";
import rawAnnouncements from "@/announcements.json";

// ─── Storage key ──────────────────────────────────────────────────────────────
// Follows the rktb-* namespace used throughout (rktb-ann-dismissed, rktb-builder-*, etc.)
// Value: the date string of the most recent announcement the user has visited the page for.
const LS_KEY = "rktb-ann-seen";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getNewestDate(): string {
  const ann = rawAnnouncements as { date: string }[];
  if (ann.length === 0) return "";
  return ann.reduce((max, a) => (a.date > max ? a.date : max), ann[0]!.date);
}

function getSeenDate(): string {
  try {
    return localStorage.getItem(LS_KEY) ?? "";
  } catch {
    // Private/incognito mode or storage quota exceeded — treat as unseen.
    return "";
  }
}

function computeHasUnread(): boolean {
  const newest = getNewestDate();
  // Guard: if no announcements exist, never show a dot.
  if (!newest) return false;
  return newest > getSeenDate();
}

// ─── Module-level pub-sub ─────────────────────────────────────────────────────
// Topbar and AnnouncementsPage are both mounted simultaneously inside AppShell.
// When markAnnouncementsSeen() is called by the page, the Topbar subscriber
// is notified immediately so the dot disappears without a context or reload.
const subscribers = new Set<() => void>();

// Cached at module-init so the first useState() call is synchronous (no flash).
let cached: boolean = computeHasUnread();

function notifyAll(): void {
  cached = computeHasUnread(); // re-read after localStorage write
  subscribers.forEach(fn => fn());
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function markAnnouncementsSeen(): void {
  const newest = getNewestDate();
  if (!newest) return;
  try {
    localStorage.setItem(LS_KEY, newest);
  } catch {
    // Storage unavailable — dot may reappear on reload, acceptable degradation.
  }
  notifyAll();
}

export function useAnnouncementUnread(): boolean {
  const [hasUnread, setHasUnread] = useState<boolean>(() => cached);

  useEffect(() => {
    // Re-check on mount in case another tab updated localStorage between
    // module-init and this component mounting.
    setHasUnread(computeHasUnread());

    const handler = () => setHasUnread(cached);
    subscribers.add(handler);
    return () => {
      subscribers.delete(handler);
    };
  }, []);

  return hasUnread;
}
