import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Users, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/api/client";
import type { components } from "@/api/schema";

type League = components["schemas"]["LeagueResponse"];

export function DashboardPage() {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api
      .GET("/leagues")
      .then(({ data }) => setLeagues(data ?? []))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Your leagues and sessions</p>
        </div>
        <Button asChild size="sm">
          <Link to="/leagues/new">
            <Plus className="mr-1.5 h-4 w-4" />
            New league
          </Link>
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-lg border border-border bg-muted" />
          ))}
        </div>
      ) : leagues.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-20 text-center">
          <p className="text-muted-foreground">You&apos;re not in any leagues yet.</p>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link to="/leagues/new">Create your first league</Link>
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {leagues.map((league) => (
            <Link
              key={league.id}
              to={`/leagues/${league.id}`}
              className="group rounded-lg border border-border bg-card p-5 transition-colors hover:border-primary/50 hover:bg-accent"
            >
              <div className="mb-3 flex items-start justify-between">
                <h2 className="font-semibold leading-tight">{league.name}</h2>
                {league.my_role && (
                  <Badge variant="secondary" className="shrink-0 text-xs capitalize">
                    {league.my_role.toLowerCase()}
                  </Badge>
                )}
              </div>

              {league.description && (
                <p className="mb-3 line-clamp-2 text-sm text-muted-foreground">
                  {league.description}
                </p>
              )}

              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {league.member_count} {league.member_count === 1 ? "member" : "members"}
                </span>
                <span className="flex items-center gap-1">
                  <Layers className="h-3.5 w-3.5" />
                  {league.session_count} {league.session_count === 1 ? "session" : "sessions"}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
