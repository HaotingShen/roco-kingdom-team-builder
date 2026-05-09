import { useState } from "react";
import type { ReactNode } from "react";

interface SubTabsProps {
  tabs: { key: string; label: string; content: ReactNode }[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
}

/**
 * Secondary-level tab strip — visually subordinate to PageTabs.
 *
 * Same controlled/uncontrolled API as PageTabs (tabs[], activeTab, onTabChange)
 * so consumers can pick whichever level they need without learning a second
 * prop set.
 *
 * Visual differences vs PageTabs:
 *   - smaller font (text-xs sm:text-sm)
 *   - tighter padding
 *   - active marker is a pill background (bg-zinc-100) instead of an
 *     underlined bottom border
 *
 * The pill style intentionally avoids stacking two underlined rows of tabs
 * — that reads as ambiguous "are these the same level?" — and gives a clear
 * primary-vs-secondary visual hierarchy.
 *
 * Like PageTabs, only the active tab's `content` is rendered to the DOM, so
 * inactive tabs' subtree hooks don't run. Switching tabs unmounts the
 * previous content and mounts the new one.
 */
export default function SubTabs({ tabs, activeTab, onTabChange }: SubTabsProps) {
  const [internalActive, setInternalActive] = useState(tabs[0]?.key);

  // Support both controlled and uncontrolled usage.
  const active = activeTab ?? internalActive;
  const setActive = (key: string) => {
    if (onTabChange) {
      onTabChange(key);
    } else {
      setInternalActive(key);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-3">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActive(t.key)}
            aria-pressed={active === t.key}
            className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors whitespace-nowrap cursor-pointer ${
              active === t.key
                ? "bg-zinc-200 text-zinc-900 font-semibold"
                : "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div>{tabs.find((t) => t.key === active)?.content}</div>
    </div>
  );
}
