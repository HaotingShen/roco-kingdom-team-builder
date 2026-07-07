import { createBrowserRouter, createHashRouter, Navigate } from "react-router-dom";

// TapTap serves the app from an arbitrary CDN sub-path with no server-side
// fallback to index.html. Hash routing avoids the dependency on pathname
// entirely — all navigation happens via the fragment (#/en/build, #/zh/dex, etc.).
const createRouter = import.meta.env.VITE_HASH_ROUTER === "true"
  ? createHashRouter
  : createBrowserRouter;
import App from "./App";
import BuilderPage from "./features/builder/BuilderPage";
import MonsterAnalysisPage from "./features/builder/MonsterAnalysisPage";
import DexPage from "./features/dex/DexPage";
import MonsterDetailPage from "./features/dex/MonsterDetailPage";
import MoveDetailPage from "./features/dex/MoveDetailPage";
import SavedTeamPage from "./features/teams/SavedTeamPage";
import TeamsListPage from "./features/teams/TeamsListPage";
import LoginPage from "./features/auth/LoginPage";
import RegisterPage from "./features/auth/RegisterPage";
import ForgotPasswordPage from "./features/auth/ForgotPasswordPage";
import ResetPasswordPage from "./features/auth/ResetPasswordPage";
import VerifyEmailPage from "./features/auth/VerifyEmailPage";
import ConfirmEmailChangePage from "./features/auth/ConfirmEmailChangePage";
import AdminPage from "./features/admin/AdminPage";
import SettingsPage from "./features/auth/SettingsPage";
import FeedbackPage from "./features/feedback/FeedbackPage";
import ImportPage from "./features/share/ImportPage";
import AnnouncementsPage from "./features/announcements/AnnouncementsPage";

/**
 * Fallback for URLs without a locale prefix. In production, CloudFront
 * redirects "/" (302 by Accept-Language) and legacy paths (301 → /en/...)
 * before the SPA ever sees them, so this only fires in `vite dev` and the
 * TapTap hash-router build (which boots at "#/"). It must be preference-based —
 * a hardcoded /en would dump TapTap's Chinese users into English UI.
 */
function RedirectToPreferredLocale() {
  const stored = localStorage.getItem("lang");
  const lang = stored === "zh" || stored === "en"
    ? stored
    : navigator.language.startsWith("zh") ? "zh" : "en";
  return <Navigate to={`/${lang}/`} replace />;
}

// NOTE: the legacy "/build" route was deliberately dropped — the homepage
// (/{lang}/) IS the builder. CloudFront 301s legacy /build → /en/.
const router = createRouter([
  {
    path: "/:lang",
    element: <App />,
    children: [
      { index: true, element: <BuilderPage /> },
      { path: "build/analyze/:slot", element: <MonsterAnalysisPage /> },
      { path: "dex", element: <DexPage /> },
      { path: "dex/monsters/:id", element: <MonsterDetailPage /> },
      { path: "dex/moves/:id", element: <MoveDetailPage /> },
      { path: "teams", element: <TeamsListPage /> },
      { path: "teams/:id", element: <SavedTeamPage /> },
      { path: "auth/login", element: <LoginPage /> },
      { path: "auth/register", element: <RegisterPage /> },
      { path: "auth/forgot-password", element: <ForgotPasswordPage /> },
      { path: "auth/reset-password", element: <ResetPasswordPage /> },
      { path: "auth/verify", element: <VerifyEmailPage /> },
      { path: "auth/confirm-email", element: <ConfirmEmailChangePage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "feedback", element: <FeedbackPage /> },
      { path: "import", element: <ImportPage /> },
      { path: "announcements", element: <AnnouncementsPage /> },
    ]
  },
  {
    path: "*",
    element: <RedirectToPreferredLocale />
  }
]);

export default router;
