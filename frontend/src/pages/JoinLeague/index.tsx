import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Loader2, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/api/client";

/**
 * Handles invite link redemption: /join/:token
 * Automatically exchanges the token and redirects to the league.
 */
export function JoinLeaguePage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError("Invalid invite link.");
      return;
    }

    api
      .POST("/leagues/join/{token}", { params: { path: { token } } })
      .then(({ data, error: apiError }) => {
        if (apiError || !data) {
          setError("This invite link is invalid or has expired.");
          return;
        }
        navigate(`/leagues/${data.id}`, { replace: true });
      })
      .catch(() => setError("Something went wrong."));
  }, [token]);

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <Trophy className="h-8 w-8 text-muted-foreground" />
        <p className="text-muted-foreground">{error}</p>
        <Button variant="outline" onClick={() => navigate("/dashboard")}>
          Go to dashboard
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <p className="text-sm text-muted-foreground">Joining league…</p>
    </div>
  );
}
