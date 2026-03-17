import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";

export function RegisterPage() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password, displayName);
      navigate("/dashboard", { replace: true });
    } catch {
      setError("Registration failed. That email may already be in use.");
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
            Create Account
          </h1>
          <div className="mt-2 flex items-center justify-center gap-3">
            <span className="h-px w-8 bg-border" />
            <p className="font-display text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              Join and start competing
            </p>
            <span className="h-px w-8 bg-border" />
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label
              htmlFor="displayName"
              className="font-display text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
            >
              Display name
            </Label>
            <Input
              id="displayName"
              type="text"
              placeholder="The Analytician"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
              autoFocus
              className="rounded-sm border-border bg-input text-sm"
            />
          </div>

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
              minLength={8}
              className="rounded-sm border-border bg-input text-sm"
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <Button
            type="submit"
            className="w-full rounded-sm font-display text-sm font-bold uppercase tracking-[0.15em]"
            disabled={submitting}
          >
            {submitting ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-center font-display text-[11px] uppercase tracking-wider text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
