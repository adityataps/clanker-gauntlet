import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Play, Pause, WifiOff, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSessionWs, type SessionEvent } from "@/hooks/useSessionWs";
import { api } from "@/api/client";
import type { components } from "@/api/schema";

// ─── Types ────────────────────────────────────────────────────────────────────

type SessionDetail = components["schemas"]["SessionDetailResponse"];

interface TeamScore {
  team_id: string;
  team_name: string;
  team_type: "AGENT" | "HUMAN" | "EXTERNAL";
  score: number;
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
  connected: "Connected",
  ROSTER_LOCK: "Roster lock",
  NEWS_ITEM: "News",
  INJURY_UPDATE: "Injury update",
  AGENT_WINDOW_OPEN: "Agent window open",
  AGENT_WINDOW_CLOSE: "Agent window close",
  GAME_START: "Games started",
  SCORE_UPDATE: "Score update",
  WEEK_END: "Week ended",
  WAIVER_OPEN: "Waivers open",
  WAIVER_RESOLVED: "Waivers resolved",
  TRADE_PROPOSED: "Trade proposed",
  TRADE_RESOLVED: "Trade resolved",
  SEASON_END: "Season ended",
};

function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replace(/_/g, " ").toLowerCase();
}

const EVENT_COLOR: Record<string, string> = {
  WEEK_END: "text-yellow-400",
  WAIVER_RESOLVED: "text-sky-400",
  TRADE_RESOLVED: "text-violet-400",
  INJURY_UPDATE: "text-red-400",
  AGENT_WINDOW_OPEN: "text-primary",
  SEASON_END: "text-yellow-300",
  ROSTER_LOCK: "text-amber-400",
};

function statusLabel(status: string, isRunning: boolean): { label: string; cls: string } {
  if (isRunning) return { label: "Live", cls: "text-primary" };
  switch (status) {
    case "in_progress":
    case "draft_in_progress":
      return { label: "In Progress", cls: "text-foreground" };
    case "paused":
      return { label: "Paused", cls: "text-amber-400" };
    case "completed":
      return { label: "Complete", cls: "text-muted-foreground" };
    default:
      return { label: "Setup", cls: "text-muted-foreground" };
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function LiveBadge({ isConnected }: { isConnected: boolean }) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-sm border px-2 py-1 font-display text-[10px] font-semibold uppercase tracking-wider",
        isConnected ? "border-primary/30 text-primary" : "border-border text-muted-foreground"
      )}
    >
      {isConnected ? (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
        </span>
      ) : (
        <WifiOff className="h-2.5 w-2.5" />
      )}
      {isConnected ? "Live" : "Disconnected"}
    </div>
  );
}

function Scoreboard({ teams, week }: { teams: TeamScore[]; week: number }) {
  const sorted = [...teams].sort((a, b) => b.score - a.score);

  return (
    <div className="rounded-sm border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-display text-xs font-bold uppercase tracking-[0.15em] text-foreground">
          Scoreboard
        </span>
        {week > 0 && (
          <span className="font-display text-[10px] uppercase tracking-wider text-muted-foreground">
            Wk {week}
          </span>
        )}
      </div>

      {sorted.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <p className="font-display text-xs uppercase tracking-wider text-muted-foreground">
            No teams yet
          </p>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {sorted.map((t, i) => (
            <div key={t.team_id} className="flex items-center gap-3 px-4 py-3 hover:bg-accent">
              <span className="w-5 shrink-0 font-display text-lg font-bold leading-none text-muted-foreground/50">
                {i + 1}
              </span>
              <div className="shrink-0 text-muted-foreground">
                {t.team_type === "AGENT" ? (
                  <Bot className="h-3.5 w-3.5" />
                ) : (
                  <User className="h-3.5 w-3.5" />
                )}
              </div>
              <span className="flex-1 truncate text-sm font-medium">{t.team_name}</span>
              <span className="font-mono text-sm font-medium tabular-nums text-foreground">
                {t.score.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EventLog({ events }: { events: EventEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-sm border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-display text-xs font-bold uppercase tracking-[0.15em] text-foreground">
          Event Log
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">{events.length} events</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {events.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="font-display text-xs uppercase tracking-wider text-muted-foreground">
              Waiting for events…
            </p>
          </div>
        ) : (
          <div className="space-y-0">
            {events.map((ev) => (
              <div
                key={ev.id}
                className="event-entry flex items-start gap-4 border-b border-border/40 py-2.5 last:border-0"
              >
                <span className="mt-px shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                  {ev.receivedAt.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                    hour12: false,
                  })}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "font-display text-xs font-semibold uppercase tracking-wide",
                        EVENT_COLOR[ev.type] ?? "text-foreground"
                      )}
                    >
                      {eventLabel(ev.type)}
                    </span>
                    {ev.seq !== undefined && (
                      <span className="font-mono text-[10px] text-muted-foreground/60">
                        #{ev.seq}
                      </span>
                    )}
                  </div>
                  {ev.payload.description != null && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {String(ev.payload.description)}
                    </p>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function SessionPage() {
  const { leagueId, sessionId } = useParams<{
    leagueId: string;
    sessionId: string;
  }>();
  const navigate = useNavigate();

  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [teams, setTeams] = useState<TeamScore[]>([]);
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [actionPending, setActionPending] = useState(false);

  // Load session details + build initial scoreboard
  useEffect(() => {
    if (!sessionId) return;
    api
      .GET("/sessions/{session_id}", { params: { path: { session_id: sessionId } } })
      .then(({ data }) => {
        if (!data) return;
        setSessionDetail(data);
        setTeams(
          data.teams.map((t) => ({
            team_id: t.id,
            team_name: t.name,
            team_type: t.type.toUpperCase() as TeamScore["team_type"],
            score: 0,
          }))
        );
      });
  }, [sessionId]);

  const handleEvent = useCallback((ev: SessionEvent) => {
    setEvents((prev) => [
      ...prev.slice(-199),
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

  async function handleStart() {
    if (!sessionId) return;
    setActionPending(true);
    try {
      const { data } = await api.POST("/sessions/{session_id}/start", {
        params: { path: { session_id: sessionId } },
      });
      if (data) setSessionDetail(data);
    } finally {
      setActionPending(false);
    }
  }

  async function handlePause() {
    if (!sessionId) return;
    setActionPending(true);
    try {
      const { data } = await api.POST("/sessions/{session_id}/pause", {
        params: { path: { session_id: sessionId } },
      });
      if (data) setSessionDetail(data);
    } finally {
      setActionPending(false);
    }
  }

  if (!sessionId || !leagueId) return null;

  const canStart =
    sessionDetail && !sessionDetail.is_running && sessionDetail.status !== "completed";
  const canPause = sessionDetail?.is_running;
  const status = sessionDetail ? statusLabel(sessionDetail.status, sessionDetail.is_running) : null;

  return (
    <div
      className="mx-auto flex max-w-screen-xl flex-col px-4 py-8"
      style={{ height: "calc(100vh - 48px)" }}
    >
      {/* Header */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            className="flex items-center gap-1.5 font-display text-xs uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => navigate(`/leagues/${leagueId}`)}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            League
          </button>
          <span className="text-border">·</span>
          <h1 className="font-display text-xl font-bold uppercase tracking-wide text-foreground">
            {sessionDetail?.name ?? "Session"}
          </h1>
          {status && (
            <span className={cn("font-display text-[10px] uppercase tracking-wider", status.cls)}>
              {status.label}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {canStart && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 rounded-sm font-display text-xs font-bold uppercase tracking-wide"
              onClick={handleStart}
              disabled={actionPending}
            >
              <Play className="h-3 w-3" />
              Start
            </Button>
          )}
          {canPause && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 rounded-sm font-display text-xs font-bold uppercase tracking-wide"
              onClick={handlePause}
              disabled={actionPending}
            >
              <Pause className="h-3 w-3" />
              Pause
            </Button>
          )}
          <LiveBadge isConnected={isConnected} />
        </div>
      </div>

      {/* Body — two-column */}
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1fr_300px]">
        {/* Left — event log */}
        <EventLog events={events} />

        {/* Right — scoreboard + actions */}
        <div className="flex flex-col gap-3">
          <Scoreboard teams={teams} week={sessionDetail?.current_week ?? 0} />

          {/* Actions */}
          <div className="rounded-sm border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <span className="font-display text-xs font-bold uppercase tracking-[0.15em] text-foreground">
                Actions
              </span>
            </div>
            <div className="p-2">
              <Link
                to={`/leagues/${leagueId}/sessions/${sessionId}/lineup`}
                className="flex items-center justify-between rounded-sm px-3 py-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <span className="font-display uppercase tracking-wider">Edit lineup</span>
                <ArrowLeft className="h-3 w-3 rotate-180" />
              </Link>
              <Link
                to={`/leagues/${leagueId}/sessions/${sessionId}/waivers`}
                className="flex items-center justify-between rounded-sm px-3 py-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <span className="font-display uppercase tracking-wider">Waiver claims</span>
                <ArrowLeft className="h-3 w-3 rotate-180" />
              </Link>
              <Link
                to={`/leagues/${leagueId}/sessions/${sessionId}/trades`}
                className="flex items-center justify-between rounded-sm px-3 py-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <span className="font-display uppercase tracking-wider">Trades</span>
                <ArrowLeft className="h-3 w-3 rotate-180" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
