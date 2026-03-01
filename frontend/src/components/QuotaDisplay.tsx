import { useI18n } from "@/i18n";
import { useAuthStore, type QuotaInfo } from "@/features/auth/authStore";

interface QuotaDisplayProps {
  quota: QuotaInfo | null;
  variant: "menu" | "inline";
}

function tierBadgeClasses(tier: string, isUnverified: boolean): string {
  if (isUnverified) return "bg-amber-100 text-amber-700";
  switch (tier) {
    case "anonymous": return "bg-zinc-100 text-zinc-600";
    case "guest":     return "bg-zinc-200 text-zinc-700";
    case "free":      return "bg-blue-100 text-blue-700";
    case "premium":   return "bg-amber-100 text-amber-700";
    case "unlimited": return "bg-purple-100 text-purple-700";
    default:          return "bg-zinc-100 text-zinc-600";
  }
}

function formatUsage(used: number, limit: number, t: (key: string) => string): string {
  if (limit === -1) return t("quota.unlimited");
  return `${used}/${limit}`;
}

export default function QuotaDisplay({ quota, variant }: QuotaDisplayProps) {
  const { t } = useI18n();
  const { user } = useAuthStore();

  if (!quota) return null;

  // Registered user whose email is not yet verified — backend enforces guest-tier limits
  const isUnverified = !!user && !user.is_guest && !user.email_verified;

  if (variant === "inline") {
    if (quota.teams_limit === -1) return null;
    return (
      <span className="text-sm text-zinc-500">
        {quota.teams_used}/{quota.teams_limit} {t("quota.teams")}
      </span>
    );
  }

  // variant === "menu"
  return (
    <div className="px-3 py-2 border-b border-zinc-100 space-y-1.5">
      {/* Tier badge */}
      <div className="flex items-center gap-1.5">
        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${tierBadgeClasses(quota.tier, isUnverified)}`}>
          {isUnverified ? t("quota.unverified") : (t(`quota.${quota.tier}`) || quota.tier)}
        </span>
      </div>

      {/* Analysis usage */}
      <div className="flex items-center justify-between text-xs text-zinc-600">
        <span>{t("quota.analyses")}</span>
        <span className={
          quota.daily_limit !== -1 && quota.daily_used >= quota.daily_limit
            ? "text-red-600 font-medium"
            : "text-zinc-700"
        }>
          {formatUsage(quota.daily_used, quota.daily_limit, t)} {quota.daily_limit !== -1 ? t("quota.today") : ""}
        </span>
      </div>

      {/* Team usage - only for non-anonymous */}
      {!quota.is_anonymous && (
        <div className="flex items-center justify-between text-xs text-zinc-600">
          <span>{t("quota.teams")}</span>
          <span className={
            quota.teams_limit !== -1 && quota.teams_used >= quota.teams_limit
              ? "text-red-600 font-medium"
              : "text-zinc-700"
          }>
            {formatUsage(quota.teams_used, quota.teams_limit, t)}
          </span>
        </div>
      )}
    </div>
  );
}
