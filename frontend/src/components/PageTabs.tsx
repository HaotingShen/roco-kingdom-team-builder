import { useState } from "react";
import type { ReactNode } from "react";

interface PageTabsProps {
  tabs: { key: string; label: string; content: ReactNode }[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
}

export default function PageTabs({
  tabs,
  activeTab,
  onTabChange,
}: PageTabsProps) {
  const [internalActive, setInternalActive] = useState(tabs[0]?.key);

  // Support both controlled and uncontrolled usage
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
      <div className="flex gap-2 border-b mb-3">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${active === t.key ? "border-zinc-900" : "border-transparent text-zinc-500"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div>{tabs.find(t => t.key === active)?.content}</div>
    </div>
  );
}