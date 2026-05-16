import type { ReactNode } from "react";

// Update this date to extend or retire the "New" badge.
const NEW_BADGE_EXPIRY = new Date("2026-06-30");

const showBadge = new Date() < NEW_BADGE_EXPIRY;

export default function HotLabel({ children }: { children: ReactNode }) {
  if (!showBadge) return <>{children}</>;
  return (
    <span className="relative inline-flex items-center">
      {children}
      <span className="absolute -top-1 -right-4 text-rose-500 text-[9px] font-bold leading-none select-none pointer-events-none rotate-[20deg]">
        New
      </span>
    </span>
  );
}
