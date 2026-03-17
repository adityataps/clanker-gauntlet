import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Users, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
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
    <div className="mx-auto max-w-screen-xl px-4 py-10">
      {/* Header */}
      <div className="mb-8 flex items-end justify-between border-b border-border pb-6">
        <div>
          <p className="mb-1 font-display text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            Overview
          </p>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide text-foreground">
            Your Leagues
          </h1>
        </div>
        <Button
          asChild
          size="sm"
          className="rounded-sm font-display text-xs font-bold uppercase tracking-[0.1em]"
        >
          <Link to="/leagues/new">
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            New league
          </Link>
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-36 animate-pulse rounded-sm border border-border bg-card" />
          ))}
        </div>
      ) : leagues.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-sm border border-dashed border-border py-24 text-center">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-sm border border-border text-muted-foreground">
            <Layers className="h-4 w-4" />
          </div>
          <p className="text-sm text-muted-foreground">You&apos;re not in any leagues yet.</p>
          <Button asChild variant="outline" size="sm" className="mt-4 rounded-sm text-xs">
            <Link to="/leagues/new">Create your first league</Link>
          </Button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {leagues.map((league) => (
            <Link
              key={league.id}
              to={`/leagues/${league.id}`}
              className="group relative overflow-hidden rounded-sm border border-border bg-card p-5 transition-all hover:border-primary/30 hover:bg-accent"
            >
              {/* Hover accent stripe */}
              <div className="absolute inset-x-0 top-0 h-px bg-primary opacity-0 transition-opacity duration-200 group-hover:opacity-100" />

              <div className="mb-3 flex items-start justify-between gap-3">
                <h2 className="font-display text-xl font-bold uppercase tracking-wide leading-tight text-foreground">
                  {league.name}
                </h2>
                {league.my_role && (
                  <span className="mt-0.5 shrink-0 rounded-sm border border-border px-1.5 py-0.5 font-display text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                    {league.my_role.toLowerCase()}
                  </span>
                )}
              </div>

              {league.description && (
                <p className="mb-4 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                  {league.description}
                </p>
              )}

              <div className="flex items-center gap-5 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <Users className="h-3 w-3" />
                  <span className="font-mono tabular-nums">{league.member_count}</span>
                  <span>{league.member_count === 1 ? "member" : "members"}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <Layers className="h-3 w-3" />
                  <span className="font-mono tabular-nums">{league.session_count}</span>
                  <span>{league.session_count === 1 ? "session" : "sessions"}</span>
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
