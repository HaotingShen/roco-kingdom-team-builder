import { useState, useRef, useEffect } from "react";
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
  const [showFade, setShowFade] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Support both controlled and uncontrolled usage
  const active = activeTab ?? internalActive;
  const setActive = (key: string) => {
    if (onTabChange) {
      onTabChange(key);
    } else {
      setInternalActive(key);
    }
  };

  const handleTabClick = (key: string, btn: HTMLButtonElement, idx: number) => {
    setActive(key);

    const container = scrollRef.current;
    if (!container) return;

    // Clicked tab is off-screen to the left — scroll it into view
    if (btn.offsetLeft < container.scrollLeft) {
      container.scrollTo({ left: Math.max(0, btn.offsetLeft - 8), behavior: "smooth" });
      return;
    }

    const containerRight = container.scrollLeft + container.clientWidth;

    // Clicked tab is not fully visible to the right — scroll to fully reveal it
    if (btn.offsetLeft + btn.offsetWidth > containerRight) {
      container.scrollTo({
        left: btn.offsetLeft + btn.offsetWidth + 8 - container.clientWidth,
        behavior: "smooth",
      });
      return;
    }

    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>("button"));

    // Next tab barely/not visible → scroll right to peek it
    const nextBtn = buttons[idx + 1];
    if (nextBtn) {
      const nextVisiblePx = Math.max(0, containerRight - nextBtn.offsetLeft);
      if (nextVisiblePx < 30) {
        container.scrollTo({
          left: nextBtn.offsetLeft + 40 - container.clientWidth,
          behavior: "smooth",
        });
        return;
      }
    }

    // Previous tab barely/not visible → scroll left to peek it
    const prevBtn = buttons[idx - 1];
    if (prevBtn) {
      const prevVisiblePx = Math.max(0, prevBtn.offsetLeft + prevBtn.offsetWidth - container.scrollLeft);
      if (prevVisiblePx < 30) {
        container.scrollTo({
          left: Math.max(0, prevBtn.offsetLeft + prevBtn.offsetWidth - 40),
          behavior: "smooth",
        });
      }
    }
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const check = () => {
      setShowFade(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
    };

    check();
    el.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check, { passive: true });
    return () => {
      el.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, []);

  return (
    <div>
      <div className="relative">
        <div
          ref={scrollRef}
          className="flex gap-2 border-b mb-3 overflow-x-auto overflow-y-hidden scrollbar-hide"
        >
          {tabs.map((t, idx) => (
            <button
              key={t.key}
              onClick={(e) => handleTabClick(t.key, e.currentTarget, idx)}
              className={`px-3 py-2 text-sm border-b-2 -mb-px whitespace-nowrap shrink-0 ${active === t.key ? "border-zinc-900" : "border-transparent text-zinc-500"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {showFade && (
          <div className="pointer-events-none absolute right-0 top-0 h-full w-12 bg-gradient-to-l from-white to-transparent" />
        )}
      </div>
      <div>
        {tabs.map(t => (
          <div key={t.key} className={t.key === active ? "" : "hidden"}>
            {t.content}
          </div>
        ))}
      </div>
    </div>
  );
}
