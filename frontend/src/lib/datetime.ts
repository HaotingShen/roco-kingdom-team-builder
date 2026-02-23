export function formatLocal(iso?: string | null, locale = navigator.language) {
  if (!iso) return "—";
  const d = new Date(iso);
  // Always display in Beijing (China) time zone (UTC+8)
  return new Intl.DateTimeFormat(locale, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(d);
}