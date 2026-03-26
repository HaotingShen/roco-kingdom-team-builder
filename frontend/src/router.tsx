import { createBrowserRouter } from "react-router-dom";
import App from "./App";
import BuilderPage from "./features/builder/BuilderPage";
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

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <BuilderPage /> },
      { path: "build", element: <BuilderPage /> },
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
      { path: "import", element: <ImportPage /> }
    ]
  }
]);

export default router;