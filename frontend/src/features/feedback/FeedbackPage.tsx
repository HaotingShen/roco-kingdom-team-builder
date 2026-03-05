import { useState, useEffect, useRef } from "react";
import { useI18n } from "@/i18n";
import { useAuthStore } from "@/features/auth/authStore";
import { api } from "@/lib/api";

type Category = "bug" | "feature" | "experience" | "other";

const CATEGORIES: Category[] = ["bug", "feature", "experience", "other"];

const CAT_KEYS: Record<Category, string> = {
  bug: "feedback.cat_bug",
  feature: "feedback.cat_feature",
  experience: "feedback.cat_experience",
  other: "feedback.cat_other",
};

const CAT_COLORS: Record<Category, string> = {
  bug: "border-red-300 bg-red-500 text-white shadow-red-100",
  feature: "border-amber-300 bg-amber-400 text-white shadow-amber-100",
  experience: "border-purple-300 bg-purple-500 text-white shadow-purple-100",
  other: "border-zinc-400 bg-zinc-600 text-white shadow-zinc-100",
};

const CAT_COLORS_INACTIVE: Record<Category, string> = {
  bug: "border-red-200 text-red-600 hover:bg-red-50",
  feature: "border-amber-200 text-amber-700 hover:bg-amber-50",
  experience: "border-purple-200 text-purple-600 hover:bg-purple-50",
  other: "border-zinc-300 text-zinc-600 hover:bg-zinc-50",
};

type Status = "idle" | "pending" | "success" | "error" | "ratelimit";

export default function FeedbackPage() {
  const { t } = useI18n();
  const { user } = useAuthStore();

  const [category, setCategory] = useState<Category>("bug");
  const [message, setMessage] = useState("");
  const [replyEmail, setReplyEmail] = useState("");
  const [honeypot, setHoneypot] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [isComposing, setIsComposing] = useState(false);
  const preCompositionLength = useRef(0);

  // Pre-fill reply email for registered users
  useEffect(() => {
    if (user && !user.is_guest && user.email) {
      setReplyEmail(user.email);
    }
  }, [user]);

  // Freeze the displayed count during IME composition so it doesn't jump with pinyin keystrokes
  const charCount = isComposing ? preCompositionLength.current : message.length;
  const isMessageValid = message.length >= 10 && message.length <= 2000;
  const canSubmit = isMessageValid && status !== "pending";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setStatus("pending");
    try {
      await api.post("/feedback", {
        category,
        message,
        reply_email: replyEmail.trim() || null,
        website: honeypot, // honeypot
      });
      setStatus("success");
      setMessage("");
    } catch (err: any) {
      if (err?.response?.status === 429) {
        setStatus("ratelimit");
      } else {
        setStatus("error");
      }
    }
  };

  const handleSubmitAnother = () => {
    setStatus("idle");
    setMessage("");
  };

  const statusBanner = () => {
    if (status === "success") {
      return (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700 flex items-center justify-between gap-3">
          <span>{t("feedback.success")}</span>
          <button
            onClick={handleSubmitAnother}
            className="text-emerald-700 underline underline-offset-2 hover:text-emerald-900 whitespace-nowrap cursor-pointer text-xs font-medium"
          >
            {t("feedback.submitAnother")}
          </button>
        </div>
      );
    }
    if (status === "ratelimit") {
      return (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
          {t("feedback.errorRateLimit")}
        </div>
      );
    }
    if (status === "error") {
      return (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {t("feedback.errorGeneric")}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="max-w-lg mx-auto py-8 px-4">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-semibold text-zinc-900">{t("feedback.title")}</h1>
        <p className="mt-2 text-sm text-zinc-500">{t("feedback.subtitle")}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Category */}
        <div>
          <p className="text-sm font-medium text-zinc-700 mb-2">{t("feedback.category")}</p>
          <div className="flex gap-2 flex-wrap">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`px-3 py-1.5 rounded-lg border text-sm font-medium transition-all cursor-pointer shadow-sm ${
                  category === cat
                    ? CAT_COLORS[cat]
                    : `bg-white ${CAT_COLORS_INACTIVE[cat]}`
                }`}
              >
                {t(CAT_KEYS[cat])}
              </button>
            ))}
          </div>
        </div>

        {/* Message */}
        <div>
          <label className="text-sm font-medium text-zinc-700 block mb-1">
            {t("feedback.message")}
          </label>
          <p className="text-xs text-zinc-400 mb-2">{t(`feedback.messageHelper_${category}`)}</p>
          <div className="relative">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onCompositionStart={() => { preCompositionLength.current = message.length; setIsComposing(true); }}
              onCompositionEnd={() => setIsComposing(false)}
              placeholder={t(`feedback.messagePlaceholder_${category}`) ?? ""}
              rows={6}
              maxLength={2000}
              className="w-full rounded-lg border-2 border-zinc-200 px-3 py-2.5 text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none focus:border-blue-400 resize-none transition-colors"
            />
            <div className="absolute bottom-2 right-3 flex items-center gap-2 text-xs text-zinc-400 pointer-events-none">
              {charCount < 10 && (
                <span className="text-amber-500">{t("feedback.charMin")}</span>
              )}
              <span className={charCount > 1900 ? "text-red-400" : ""}>
                {(t("feedback.charCount") ?? "{n}/2000").replace("{n}", String(charCount))}
              </span>
            </div>
          </div>
        </div>

        {/* Reply email */}
        <div>
          <label className="text-sm font-medium text-zinc-700 block mb-1">
            {t("feedback.replyEmail")}
          </label>
          <input
            type="email"
            value={replyEmail}
            onChange={(e) => setReplyEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-lg border-2 border-zinc-200 px-3 py-2 text-sm text-zinc-800 placeholder-zinc-400 focus:outline-none focus:border-blue-400 transition-colors"
          />
          <p className="mt-1 text-xs text-zinc-400">{t("feedback.replyEmailHint")}</p>
        </div>

        {/* Honeypot (hidden from real users) */}
        <div className="hidden" aria-hidden="true">
          <input
            type="text"
            name="website"
            value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
            tabIndex={-1}
            autoComplete="off"
          />
        </div>

        {/* Status banner — above button */}
        {statusBanner()}

        {/* Submit */}
        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full h-10 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
        >
          {status === "pending" ? t("feedback.submitting") : t("feedback.submit")}
        </button>
      </form>
    </div>
  );
}
