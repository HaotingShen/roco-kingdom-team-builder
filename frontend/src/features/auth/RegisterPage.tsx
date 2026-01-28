import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useAuthStore } from "./authStore";
import { useI18n } from "@/i18n";
import { validateUsername } from "@/lib/usernameValidator";
import EmailVerificationModal from "./EmailVerificationModal";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const { setAuth, isGuest } = useAuthStore();

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Email verification modal state
  const [showVerifyModal, setShowVerifyModal] = useState(false);
  const [verificationToken, setVerificationToken] = useState("");

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    // Username validation: 2-16 graphemes, letters/numbers/Chinese/underscores/hyphens
    const usernameError = validateUsername(username, t);
    if (usernameError) {
      newErrors.username = usernameError;
    }

    // Email validation
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = t("auth.invalidEmail");
    }

    // Password validation: 8+ chars, uppercase, lowercase, number
    if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/.test(password)) {
      newErrors.password = t("auth.passwordRequirements");
    }

    // Confirm password
    if (password !== confirmPassword) {
      newErrors.confirmPassword = t("auth.passwordMismatch");
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const registerMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.register({ username, email, password });
      return response.data;
    },
    onSuccess: (data) => {
      setAuth(data.user, data.access_token);
      toast.success(t("auth.registerSuccess"));

      // Show email verification modal (dev mode has debug_verification_token)
      if (data.debug_verification_token) {
        setVerificationToken(data.debug_verification_token);
      }
      setShowVerifyModal(true);
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail;
      if (typeof detail === "string") {
        if (detail.toLowerCase().includes("email")) {
          setErrors({ email: t("auth.emailTaken") });
        } else if (detail.toLowerCase().includes("similar")) {
          setErrors({ username: t("auth.usernameTooSimilar") });
        } else if (detail.toLowerCase().includes("username")) {
          setErrors({ username: t("auth.usernameTaken") });
        } else {
          toast.error(detail);
        }
      } else {
        toast.error(t("auth.registerFailed"));
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validateForm()) {
      registerMutation.mutate();
    }
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8 relative">
        {/* Back button */}
        <button
          onClick={() => navigate(-1)}
          className="absolute top-4 left-4 flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
          title={t("auth.backToPrevious")}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t("auth.back")}
        </button>

        <h1 className="text-2xl font-semibold text-zinc-900 mb-2 text-center mt-4">
          {t("auth.registerTitle")}
        </h1>

        {isGuest && (
          <p className="text-sm text-zinc-600 mb-6 text-center">
            {t("auth.guestPromotion")}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.username")}
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("auth.usernamePlaceholder")}
              required
              className={`w-full h-10 px-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
                errors.username ? "border-red-500" : "border-zinc-300"
              }`}
            />
            <p className={`text-xs mt-1 ${errors.username ? "text-red-500" : "text-zinc-500"}`}>
              {errors.username || t("auth.usernameHint")}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.email")}
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("auth.emailPlaceholder")}
              required
              className={`w-full h-10 px-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
                errors.email ? "border-red-500" : "border-zinc-300"
              }`}
            />
            {errors.email && (
              <p className="text-xs text-red-500 mt-1">{errors.email}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.password")}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("auth.passwordPlaceholder")}
              required
              className={`w-full h-10 px-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
                errors.password ? "border-red-500" : "border-zinc-300"
              }`}
            />
            <p className={`text-xs mt-1 ${errors.password ? "text-red-500" : "text-zinc-500"}`}>
              {t("auth.passwordRequirements")}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.confirmPassword")}
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t("auth.confirmPasswordPlaceholder")}
              required
              className={`w-full h-10 px-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
                errors.confirmPassword ? "border-red-500" : "border-zinc-300"
              }`}
            />
            {errors.confirmPassword && (
              <p className="text-xs text-red-500 mt-1">{errors.confirmPassword}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={registerMutation.isPending}
            className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
          >
            {registerMutation.isPending ? t("auth.registering") : t("auth.registerButton")}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-zinc-600">
          {t("auth.haveAccount")}{" "}
          <Link
            to="/auth/login"
            className="text-blue-600 hover:text-blue-700 font-medium"
          >
            {t("auth.loginLink")}
          </Link>
        </div>
      </div>

      {/* Email verification modal */}
      <EmailVerificationModal
        isOpen={showVerifyModal}
        onClose={() => {
          setShowVerifyModal(false);
          navigate("/build");
        }}
        initialToken={verificationToken}
      />
    </div>
  );
}
