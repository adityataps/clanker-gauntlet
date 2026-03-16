import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { LoginPage } from "@/pages/Login";
import { RegisterPage } from "@/pages/Register";
import { DashboardPage } from "@/pages/Dashboard";
import { AccountPage } from "@/pages/Account";
import { NotFoundPage } from "@/pages/NotFound";

export default function App() {
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

            {/* League + session routes — stubs for now */}
            <Route
              path="/leagues/*"
              element={<div className="p-8 text-muted-foreground">League pages coming soon.</div>}
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
