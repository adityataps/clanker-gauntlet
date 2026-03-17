import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Pause,
  WifiOff,
  Bot,
  User,
  Loader2,
  Lock,
  Newspaper,
  AlertTriangle,
  Activity,
  Trophy,
  ArrowLeftRight,
  RefreshCw,
  Zap,
  ChevronsDown,
  Flag,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionWs, type SessionEvent } from "@/hooks/useSessionWs";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { LeagueSidebar } from "@/components/LeagueSidebar";

// ─── Types ────────────────────────────────────────────────────────────────────

type SessionDetail = components["schemas"]["SessionDetailResponse"];
type Session = components["schemas"]["SessionResponse"];
type League = components["schemas"]["LeagueResponse"];

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

// ─── Event log helpers ─────────────────────────────────────────────────────────

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
  WAIVER_OPEN: "text-sky-400/70",
  TRADE_RESOLVED: "text-violet-400",
  TRADE_PROPOSED: "text-violet-400/70",
  INJURY_UPDATE: "text-red-400",
  AGENT_WINDOW_OPEN: "text-primary",
  SEASON_END: "text-yellow-300",
  ROSTER_LOCK: "text-amber-400",
  GAME_START: "text-emerald-400",
};

const EVENT_BORDER: Record<string, string> = {
  WEEK_END: "border-l-yellow-400/50",
  WAIVER_RESOLVED: "border-l-sky-400/60",
  WAIVER_OPEN: "border-l-sky-400/30",
  TRADE_RESOLVED: "border-l-violet-400/60",
  TRADE_PROPOSED: "border-l-violet-400/30",
  INJURY_UPDATE: "border-l-red-400/70",
  AGENT_WINDOW_OPEN: "border-l-primary/60",
  AGENT_WINDOW_CLOSE: "border-l-primary/20",
  SEASON_END: "border-l-yellow-300/80",
  ROSTER_LOCK: "border-l-amber-400/50",
  GAME_START: "border-l-emerald-400/40",
  NEWS_ITEM: "border-l-border/40",
};

const EVENT_ICON: Record<string, React.ReactNode> = {
  ROSTER_LOCK: <Lock className="h-2.5 w-2.5" />,
  NEWS_ITEM: <Newspaper className="h-2.5 w-2.5" />,
  INJURY_UPDATE: <AlertTriangle className="h-2.5 w-2.5" />,
  AGENT_WINDOW_OPEN: <Activity className="h-2.5 w-2.5" />,
  AGENT_WINDOW_CLOSE: <Activity className="h-2.5 w-2.5" />,
  GAME_START: <Zap className="h-2.5 w-2.5" />,
  SCORE_UPDATE: <Activity className="h-2.5 w-2.5" />,
  WAIVER_OPEN: <RefreshCw className="h-2.5 w-2.5" />,
  WAIVER_RESOLVED: <RefreshCw className="h-2.5 w-2.5" />,
  TRADE_PROPOSED: <ArrowLeftRight className="h-2.5 w-2.5" />,
  TRADE_RESOLVED: <ArrowLeftRight className="h-2.5 w-2.5" />,
  SEASON_END: <Trophy className="h-2.5 w-2.5" />,
  connected: <Flag className="h-2.5 w-2.5" />,
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

// ─── Event log ────────────────────────────────────────────────────────────────

function WeekDivider({ event }: { event: EventEntry }) {
  const week = event.payload?.week as number | undefined;
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <div className="h-px flex-1 bg-yellow-400/20" />
      <span className="font-display text-[8px] font-bold uppercase tracking-[0.25em] text-yellow-400/60">
        {week != null ? `Week ${week} end` : "Week end"}
      </span>
      <div className="h-px flex-1 bg-yellow-400/20" />
    </div>
  );
}

function EventRow({ event }: { event: EventEntry }) {
  const borderCls = EVENT_BORDER[event.type] ?? "border-l-border/20";
  const colorCls = EVENT_COLOR[event.type] ?? "text-foreground";
  const icon = EVENT_ICON[event.type];

  return (
    <div
      className={cn(
        "flex items-start gap-3 border-l-2 px-4 py-2 transition-colors hover:bg-accent/30",
        borderCls
      )}
    >
      <span className="mt-0.5 w-14 shrink-0 font-mono text-[9px] tabular-nums text-muted-foreground/40">
        {event.receivedAt.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })}
      </span>
      {icon && <span className={cn("mt-0.5 shrink-0", colorCls)}>{icon}</span>}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span
            className={cn(
              "font-display text-[10px] font-semibold uppercase tracking-wide",
              colorCls
            )}
          >
            {eventLabel(event.type)}
          </span>
          {event.seq !== undefined && (
            <span className="font-mono text-[9px] text-muted-foreground/40">#{event.seq}</span>
          )}
        </div>
        {event.payload?.description != null && (
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground/70">
            {String(event.payload.description)}
          </p>
        )}
      </div>
    </div>
  );
}

function EventLog({ events }: { events: EventEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (!autoScroll) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length, autoScroll]);

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-sm border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-display text-xs font-bold uppercase tracking-[0.15em] text-foreground">
          Event Log
        </span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground/60">
            {events.length}
          </span>
          <button
            onClick={() => setAutoScroll((v) => !v)}
            className={cn(
              "flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-display text-[9px] uppercase tracking-wider transition-colors",
              autoScroll ? "text-primary" : "text-muted-foreground/50 hover:text-muted-foreground"
            )}
            title={autoScroll ? "Auto-scroll on" : "Auto-scroll off"}
          >
            <ChevronsDown className="h-2.5 w-2.5" />
            Auto
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1 w-1 animate-pulse rounded-full bg-primary/30"
                  style={{ animationDelay: `${i * 200}ms` }}
                />
              ))}
            </div>
            <p className="font-mono text-[10px] text-muted-foreground/40">waiting for events</p>
          </div>
        ) : (
          <div>
            {events.map((ev) =>
              ev.type === "WEEK_END" ? (
                <WeekDivider key={ev.id} event={ev} />
              ) : (
                <EventRow key={ev.id} event={ev} />
              )
            )}
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

  const [league, setLeague] = useState<League | null>(null);
  const [leagueSessions, setLeagueSessions] = useState<Session[]>([]);

  // Load session details
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

  // Load league + sibling sessions for sidebar
  useEffect(() => {
    if (!leagueId) return;
    api
      .GET("/leagues/{league_id}", { params: { path: { league_id: leagueId } } })
      .then(({ data }) => setLeague(data ?? null));
    api
      .GET("/leagues/{league_id}/sessions", { params: { path: { league_id: leagueId } } })
      .then(({ data }) => setLeagueSessions(data ?? []));
  }, [leagueId]);

  const handleEvent = useCallback((ev: SessionEvent) => {
    setEvents((prev) => [
      ...prev.slice(-199),
      {
        id: `${Date.now()}-${Math.random()}`,
        type: ev.type,
        seq: ev.seq,
        payload: ev.payload ?? {},
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

  const progressPct =
    sessionDetail && sessionDetail.script.total_events > 0
      ? Math.min((sessionDetail.current_seq / sessionDetail.script.total_events) * 100, 100)
      : 0;

  return (
    <div className="flex" style={{ height: "calc(100vh - 48px)" }}>
      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      {league && (
        <LeagueSidebar
          league={league}
          sessions={leagueSessions}
          activeSessionId={sessionId}
          onNavigateSessions={() =>
            navigate(`/leagues/${leagueId}`, { state: { activeView: "sessions" } })
          }
          onNavigateMembers={() =>
            navigate(`/leagues/${leagueId}`, { state: { activeView: "members" } })
          }
          onNavigateSettings={
            league.my_role === "manager"
              ? () => navigate(`/leagues/${leagueId}`, { state: { activeView: "settings" } })
              : undefined
          }
          onBack={() => navigate(`/leagues/${leagueId}`)}
          backLabel="League"
          memberCount={league.member_count}
        />
      )}

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden px-4 py-6">
        {/* Header */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {/* Return to league — replaces the old collapse toggle */}
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

          <div className="flex items-center gap-2.5">
            {(canStart || canPause) && (
              <button
                onClick={canPause ? handlePause : handleStart}
                disabled={actionPending}
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-sm border transition-all",
                  canPause
                    ? "border-primary/40 bg-primary/10 text-primary hover:bg-primary/20 active:scale-95"
                    : "border-border bg-card text-foreground hover:bg-accent active:scale-95"
                )}
                title={canPause ? "Pause session" : "Start session"}
              >
                {actionPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : canPause ? (
                  <Pause className="h-3.5 w-3.5" />
                ) : (
                  <Play className="h-3.5 w-3.5 translate-x-px" />
                )}
              </button>
            )}
            <LiveBadge isConnected={isConnected} />
          </div>
        </div>

        {/* Progress bar */}
        {sessionDetail && sessionDetail.current_seq > 0 && (
          <div className="mb-4 flex items-center gap-3">
            <span className="w-12 shrink-0 font-display text-[9px] uppercase tracking-wider text-muted-foreground/60">
              Wk {sessionDetail.current_week}
            </span>
            <div className="h-0.5 flex-1 overflow-hidden rounded-full bg-border/60">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-700",
                  sessionDetail.is_running ? "bg-primary/60" : "bg-muted-foreground/40"
                )}
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <span className="w-20 shrink-0 text-right font-mono text-[9px] tabular-nums text-muted-foreground/40">
              {sessionDetail.current_seq.toLocaleString()} /{" "}
              {sessionDetail.script.total_events.toLocaleString()}
            </span>
          </div>
        )}

        {/* Body — two-column */}
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1fr_300px]">
          <EventLog events={events} />

          <div className="flex flex-col gap-3">
            <Scoreboard teams={teams} week={sessionDetail?.current_week ?? 0} />

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
    </div>
  );
}
