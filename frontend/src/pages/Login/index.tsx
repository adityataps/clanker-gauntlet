import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((s) => s.login);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/dashboard";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch {
      setError("Invalid email or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Brand mark */}
        <div className="mb-10 text-center">
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center bg-primary font-display text-base font-bold text-primary-foreground">
            CG
          </div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-[0.08em] text-foreground">
            Clanker Gauntlet
          </h1>
          <div className="mt-2 flex items-center justify-center gap-3">
            <span className="h-px w-8 bg-border" />
            <p className="font-display text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              Sign in to your account
            </p>
            <span className="h-px w-8 bg-border" />
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label
              htmlFor="email"
              className="font-display text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
            >
              Email
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              className="rounded-sm border-border bg-input text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <Label
              htmlFor="password"
              className="font-display text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
            >
              Password
            </Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="rounded-sm border-border bg-input text-sm"
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <Button
            type="submit"
            className="w-full rounded-sm font-display text-sm font-bold uppercase tracking-[0.15em]"
            disabled={submitting}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center font-display text-[11px] uppercase tracking-wider text-muted-foreground">
          No account?{" "}
          <Link to="/register" className="text-primary hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
