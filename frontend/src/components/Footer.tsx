import { NavLink } from "react-router-dom";
import { useI18n } from "@/i18n";

export default function Footer() {
  const { t } = useI18n();
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-zinc-200 bg-zinc-50 px-6 py-5 mt-8 text-xs text-zinc-500">
      <div className="max-w-4xl">
        <p>{t("footer.disclaimer")}</p>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span>{t("footer.qqGroup")}</span>
        <span>·</span>
        <span>{t("footer.wechatGroup")}</span>
        <span className="hidden lg:inline">·</span>
        <span>{t("footer.business")}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span>© {year} RK Team Builder · 洛手配队器</span>
        <NavLink to="/feedback" className="hover:text-zinc-700 underline underline-offset-2">
          {t("footer.feedback")}
        </NavLink>
      </div>
    </footer>
  );
}
