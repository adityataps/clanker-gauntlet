import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { LoginPage } from "@/pages/Login";
import { RegisterPage } from "@/pages/Register";
import { DashboardPage } from "@/pages/Dashboard";
import { AccountPage } from "@/pages/Account";
import { LeagueNewPage } from "@/pages/LeagueNew";
import { LeaguePage } from "@/pages/League";
import { SessionPage } from "@/pages/Session";
import { JoinLeaguePage } from "@/pages/JoinLeague";
import { LineupPage } from "@/pages/Lineup";
import { useAuthStore } from "@/store/authStore";
import { NotFoundPage } from "@/pages/NotFound";

export default function App() {
  const initAuth = useAuthStore((s) => s.initAuth);

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Authenticated routes — wrapped in AppShell (Navbar + layout) */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/account" element={<AccountPage />} />

            {/* Invite redemption */}
            <Route path="/join/:token" element={<JoinLeaguePage />} />

            {/* League pages */}
            <Route path="/leagues/new" element={<LeagueNewPage />} />
            <Route path="/leagues/:leagueId" element={<LeaguePage />} />

            {/* Session pages */}
            <Route path="/leagues/:leagueId/sessions/:sessionId" element={<SessionPage />} />

            {/* Sub-session pages — stubs until Phase 2 UI lands */}
            <Route path="/leagues/:leagueId/sessions/:sessionId/lineup" element={<LineupPage />} />
            <Route
              path="/leagues/:leagueId/sessions/:sessionId/waivers"
              element={
                <div className="p-8 text-muted-foreground">Waiver claims — coming soon.</div>
              }
            />
            <Route
              path="/leagues/:leagueId/sessions/:sessionId/trades"
              element={<div className="p-8 text-muted-foreground">Trades — coming soon.</div>}
            />

            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>

        {/* Catch-all for unmatched public paths */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
