import { useEffect } from "react";
import rawAnnouncements from "@/announcements.json";
import { useI18n } from "@/i18n";
import { markAnnouncementsSeen } from "@/hooks/useAnnouncementUnread";
import { useSeoMeta } from "@/hooks/useSeoMeta";

interface Announcement {
  id: string;
  type: "info" | "warning" | "critical";
  en: string;
  zh: string;
  date: string;
  expiresAt?: string;
}

const TYPE_BADGE: Record<"info" | "warning" | "critical", string> = {
  info:     "bg-blue-50 text-blue-700 border border-blue-200",
  warning:  "bg-amber-50 text-amber-700 border border-amber-200",
  critical: "bg-red-50 text-red-700 border border-red-200",
};

const TYPE_LABEL: Record<"info" | "warning" | "critical", Record<"en" | "zh", string>> = {
  info:     { en: "Info",    zh: "公告" },
  warning:  { en: "Warning", zh: "注意" },
  critical: { en: "Notice",  zh: "重要" },
};

const sorted = (rawAnnouncements as Announcement[])
  .slice()
  .sort((a, b) => b.date.localeCompare(a.date));

export default function AnnouncementsPage() {
  const { lang, t } = useI18n();

  useSeoMeta({
    title: lang === "zh"
      ? "更新公告 | 洛克王国：世界配队器"
      : "What's New | RK Team Builder",
    description: lang === "zh"
      ? "洛手配队器功能更新日志：查看最新功能上线、数据同步与平衡性调整公告。"
      : "RK Team Builder changelog: latest feature releases, game data syncs, and balance patch announcements.",
    canonicalPath: "/announcements",
  });

  useEffect(() => {
    markAnnouncementsSeen();
  }, []);

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-zinc-800 mb-6">
        {t("announcement.pageTitle")}
      </h1>

      {sorted.length === 0 ? (
        <p className="text-zinc-500 text-sm">{t("announcement.noAnnouncements")}</p>
      ) : (
        <div className="space-y-3">
          {sorted.map(ann => {
            const type = ann.type === "info" || ann.type === "warning" || ann.type === "critical"
              ? ann.type
              : "info";
            const text = lang === "zh" && ann.zh ? ann.zh : ann.en;
            return (
              <div key={ann.id} className="border border-zinc-200 rounded-lg p-4 bg-white">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${TYPE_BADGE[type]}`}>
                    {TYPE_LABEL[type][lang]}
                  </span>
                  <span className="text-xs text-zinc-400">{ann.date}</span>
                </div>
                <p className="text-sm text-zinc-700 leading-relaxed">{text}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
