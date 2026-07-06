import type { ReactNode } from "react";

// Small "Hot" popularity badge for drawing attention to notable features.
// Unlike a "New" badge this is evergreen (no auto-expiry) — it signals
// popularity/importance rather than recency. To retire it at a call site,
// remove the <HotLabel> wrapper there; to hide it everywhere, gate the return
// on a date/flag like the old NEW badge did.
export default function HotLabel({ children }: { children: ReactNode }) {
  return (
    <span className="relative inline-flex items-center">
      {children}
      <span className="absolute -top-1 -right-4 text-rose-500 text-[9px] font-bold leading-none select-none pointer-events-none rotate-[20deg]">
        Hot
      </span>
    </span>
  );
}
