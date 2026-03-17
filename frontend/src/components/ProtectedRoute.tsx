import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

/**
 * Wraps authenticated routes. While a stored token is being validated on
 * startup, renders nothing (avoids flash of protected content). Once
 * validation completes, either renders the route or redirects to /login.
 */
export function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  const isInitializing = useAuthStore((s) => s.isInitializing);
  const location = useLocation();

  if (isInitializing) return null;

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
