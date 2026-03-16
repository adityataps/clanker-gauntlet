import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Loader2, Wifi, WifiOff, Activity, Trophy, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useSessionWs, type SessionEvent } from "@/hooks/useSessionWs";

// ─── Types ────────────────────────────────────────────────────────────────────

interface TeamScore {
  team_id: string;
  team_name: string;
  team_type: "AGENT" | "HUMAN" | "EXTERNAL";
  score: number;
  record?: string;
}

interface EventEntry {
  id: string;
  type: string;
  seq?: number;
  payload: Record<string, unknown>;
  receivedAt: Date;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const EVENT_LABELS: Record<string, string> = {
  connected: "Connected to session",
  ROSTER_LOCK: "Rosters locked",
  NEWS_ITEM: "News",
  INJURY_UPDATE: "Injury update",
  AGENT_WINDOW_OPEN: "Agent window opened",
  AGENT_WINDOW_CLOSE: "Agent window closed",
  GAME_START: "Games started",
  SCORE_UPDATE: "Score update",
  WEEK_END: "Week ended",
  WAIVER_OPEN: "Waivers opened",
  WAIVER_RESOLVED: "Waivers resolved",
  TRADE_PROPOSED: "Trade proposed",
  TRADE_RESOLVED: "Trade resolved",
  SEASON_END: "Season ended",
};

function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replace(/_/g, " ").toLowerCase();
}

const EVENT_ACCENT: Record<string, string> = {
  WEEK_END: "text-yellow-400",
  WAIVER_RESOLVED: "text-blue-400",
  TRADE_RESOLVED: "text-purple-400",
  INJURY_UPDATE: "text-red-400",
  AGENT_WINDOW_OPEN: "text-green-400",
  SEASON_END: "text-yellow-300",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function ConnectionBadge({ isConnected }: { isConnected: boolean }) {
  return (
    <Badge
      variant="outline"
      className={`gap-1.5 text-xs ${isConnected ? "border-green-500/40 text-green-400" : "border-red-500/40 text-red-400"}`}
    >
      {isConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
      {isConnected ? "Live" : "Disconnected"}
    </Badge>
  );
}

function TeamTypeIcon({ type }: { type: TeamScore["team_type"] }) {
  if (type === "AGENT") return <Bot className="h-4 w-4 text-muted-foreground" />;
  return <User className="h-4 w-4 text-muted-foreground" />;
}

function ScoreboardCard({ teams }: { teams: TeamScore[] }) {
  const sorted = [...teams].sort((a, b) => b.score - a.score);
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Trophy className="h-4 w-4" />
          Scoreboard
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 pb-4">
        {sorted.length === 0 ? (
          <p className="text-sm text-muted-foreground">No teams yet.</p>
        ) : (
          sorted.map((t, i) => (
            <div
              key={t.team_id}
              className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-accent"
            >
              <div className="flex items-center gap-2.5">
                <span className="w-4 text-xs text-muted-foreground">{i + 1}</span>
                <TeamTypeIcon type={t.team_type} />
                <span className="text-sm font-medium">{t.team_name}</span>
                {t.record && <span className="text-xs text-muted-foreground">{t.record}</span>}
              </div>
              <span className="text-sm font-semibold tabular-nums">{t.score.toFixed(1)}</span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function EventTimeline({ events }: { events: EventEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4" />
          Event timeline
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto pb-4">
        <div className="space-y-2">
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">Waiting for events…</p>
          ) : (
            events.map((ev) => (
              <div key={ev.id} className="flex items-start gap-3 text-sm">
                <span className="mt-0.5 shrink-0 text-xs tabular-nums text-muted-foreground">
                  {ev.receivedAt.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                <div className="min-w-0">
                  <span
                    className={`font-medium capitalize ${EVENT_ACCENT[ev.type] ?? "text-foreground"}`}
                  >
                    {eventLabel(ev.type)}
                  </span>
                  {ev.seq !== undefined && (
                    <span className="ml-1.5 text-xs text-muted-foreground">seq {ev.seq}</span>
                  )}
                  {ev.payload.description != null && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {String(ev.payload.description)}
                    </p>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SessionPage() {
  const { leagueId, sessionId } = useParams<{
    leagueId: string;
    sessionId: string;
  }>();
  const navigate = useNavigate();

  const [teams] = useState<TeamScore[]>([]);
  const [events, setEvents] = useState<EventEntry[]>([]);

  const handleEvent = useCallback((ev: SessionEvent) => {
    setEvents((prev) => [
      ...prev.slice(-199), // keep last 200 events
      {
        id: `${Date.now()}-${Math.random()}`,
        type: ev.type,
        seq: ev.seq,
        payload: ev.payload,
        receivedAt: new Date(),
      },
    ]);
  }, []);

  const { isConnected } = useSessionWs(sessionId ?? null, { onEvent: handleEvent });

  if (!sessionId || !leagueId) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-1 text-muted-foreground"
          onClick={() => navigate(`/leagues/${leagueId}`)}
        >
          <ArrowLeft className="mr-1.5 h-4 w-4" />
          League
        </Button>

        <div className="flex items-center gap-2">
          <ConnectionBadge isConnected={isConnected} />
        </div>
      </div>

      {/* Body — two-column on large screens */}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Left — event timeline (main column) */}
        <div className="flex min-h-[480px] flex-col">
          <EventTimeline events={events} />
        </div>

        {/* Right — scoreboard + quick links */}
        <div className="space-y-4">
          <ScoreboardCard teams={teams} />

          <Card>
            <CardContent className="pt-4 pb-4 space-y-1">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Actions
              </p>
              <Button asChild variant="ghost" size="sm" className="w-full justify-start">
                <Link to={`/leagues/${leagueId}/sessions/${sessionId}/lineup`}>Edit lineup</Link>
              </Button>
              <Separator />
              <Button asChild variant="ghost" size="sm" className="w-full justify-start">
                <Link to={`/leagues/${leagueId}/sessions/${sessionId}/waivers`}>Waiver claims</Link>
              </Button>
              <Separator />
              <Button asChild variant="ghost" size="sm" className="w-full justify-start">
                <Link to={`/leagues/${leagueId}/sessions/${sessionId}/trades`}>Trades</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
