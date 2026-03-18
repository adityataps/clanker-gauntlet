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
  ChevronDown,
  ChevronRight,
  Brain,
  BarChart3,
  Swords,
  ListOrdered,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSessionWs, type SessionEvent } from "@/hooks/useSessionWs";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { LeagueSidebar } from "@/components/LeagueSidebar";

// ─── Types ────────────────────────────────────────────────────────────────────

type SessionDetail = components["schemas"]["SessionDetailResponse"];
type SessionSummary = components["schemas"]["SessionResponse"];
type League = components["schemas"]["LeagueResponse"];

// Inline types for new endpoints (until schema is regenerated)
interface PlayerScoreItem {
  player_id: string;
  points_total: number;
  stats_json: Record<string, number>;
}

interface MatchupScore {
  matchup_id: string;
  period_number: number;
  home_team_id: string;
  home_team_name: string;
  home_score: number;
  away_team_id: string;
  away_team_name: string;
  away_score: number;
  winner_team_id: string | null;
  home_players: PlayerScoreItem[];
  away_players: PlayerScoreItem[];
}

interface WeekScoresResponse {
  week: number;
  matchups: MatchupScore[];
}

interface StandingsEntry {
  rank: number;
  team_id: string;
  team_name: string;
  team_type: string;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
}

interface StandingsResponse {
  standings: StandingsEntry[];
}

interface DecisionEntry {
  id: string;
  team_id: string;
  team_name: string;
  seq: number;
  decision_type: string;
  payload: Record<string, unknown>;
  reasoning_trace: { summary: string; structured: unknown } | null;
  triggered_by: number[];
  tokens_used: number;
  created_at: string;
}

interface DecisionsResponse {
  decisions: DecisionEntry[];
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
  REACTION_WINDOW_OPEN: "Reaction window open",
  REACTION_WINDOW_CLOSE: "Reaction window closed",
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
  REACTION_WINDOW_OPEN: "text-primary/80",
  REACTION_WINDOW_CLOSE: "text-primary/40",
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
  REACTION_WINDOW_OPEN: "border-l-primary/50",
  REACTION_WINDOW_CLOSE: "border-l-primary/15",
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
  REACTION_WINDOW_OPEN: <Activity className="h-2.5 w-2.5" />,
  REACTION_WINDOW_CLOSE: <Activity className="h-2.5 w-2.5" />,
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

      <div className="flex-1 overflow-y-auto">
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

// ─── Matchups panel ───────────────────────────────────────────────────────────

function MatchupCard({ matchup }: { matchup: MatchupScore }) {
  const [expanded, setExpanded] = useState(false);
  const homeWins = matchup.winner_team_id === matchup.home_team_id;
  const awayWins = matchup.winner_team_id === matchup.away_team_id;

  return (
    <div className="rounded-sm border border-border bg-card/60">
      {/* Score row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-accent/30 transition-colors"
      >
        <div className="flex flex-1 items-center justify-between gap-2">
          <span
            className={cn(
              "flex-1 truncate text-xs font-medium",
              homeWins ? "text-foreground" : "text-muted-foreground"
            )}
          >
            {matchup.home_team_name}
          </span>
          <span
            className={cn(
              "font-mono text-sm font-semibold tabular-nums",
              homeWins ? "text-primary" : "text-foreground"
            )}
          >
            {matchup.home_score.toFixed(1)}
          </span>
        </div>
        <span className="text-muted-foreground/30 font-display text-[9px]">vs</span>
        <div className="flex flex-1 items-center justify-between gap-2 flex-row-reverse">
          <span
            className={cn(
              "flex-1 truncate text-xs font-medium text-right",
              awayWins ? "text-foreground" : "text-muted-foreground"
            )}
          >
            {matchup.away_team_name}
          </span>
          <span
            className={cn(
              "font-mono text-sm font-semibold tabular-nums",
              awayWins ? "text-primary" : "text-foreground"
            )}
          >
            {matchup.away_score.toFixed(1)}
          </span>
        </div>
        <ChevronDown
          className={cn(
            "ml-1 h-3 w-3 shrink-0 text-muted-foreground/40 transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>

      {/* Player breakdown */}
      {expanded && (
        <div className="border-t border-border grid grid-cols-2 divide-x divide-border">
          {[
            { players: matchup.home_players, label: matchup.home_team_name },
            { players: matchup.away_players, label: matchup.away_team_name },
          ].map(({ players, label }) => (
            <div key={label} className="p-2">
              {players.length === 0 ? (
                <p className="py-2 text-center font-mono text-[9px] text-muted-foreground/40">
                  no data
                </p>
              ) : (
                [...players]
                  .sort((a, b) => b.points_total - a.points_total)
                  .map((p) => (
                    <div key={p.player_id} className="flex items-center justify-between py-0.5">
                      <span className="truncate font-mono text-[9px] text-muted-foreground/60">
                        {p.player_id}
                      </span>
                      <span className="ml-2 shrink-0 font-mono text-[9px] tabular-nums text-foreground/80">
                        {p.points_total.toFixed(1)}
                      </span>
                    </div>
                  ))
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MatchupsPanel({
  scoresData,
  loading,
}: {
  scoresData: WeekScoresResponse | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/40" />
        <p className="font-mono text-[9px] text-muted-foreground/40">loading scores</p>
      </div>
    );
  }

  if (!scoresData || scoresData.matchups.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="font-display text-[10px] uppercase tracking-wider text-muted-foreground/40">
          No matchups yet
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2 p-2">
      <div className="flex items-center justify-between px-1 pb-1">
        <span className="font-display text-[9px] uppercase tracking-widest text-muted-foreground/50">
          Week {scoresData.week}
        </span>
        <span className="font-mono text-[9px] text-muted-foreground/40">
          {scoresData.matchups.length} matchup{scoresData.matchups.length !== 1 ? "s" : ""}
        </span>
      </div>
      {scoresData.matchups.map((m) => (
        <MatchupCard key={m.matchup_id} matchup={m} />
      ))}
    </div>
  );
}

// ─── Standings panel ──────────────────────────────────────────────────────────

function StandingsPanel({ data, loading }: { data: StandingsResponse | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/40" />
        <p className="font-mono text-[9px] text-muted-foreground/40">loading standings</p>
      </div>
    );
  }

  if (!data || data.standings.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="font-display text-[10px] uppercase tracking-wider text-muted-foreground/40">
          No standings yet
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Header row */}
      <div className="grid grid-cols-[20px_1fr_60px_80px] items-center gap-2 border-b border-border px-3 py-2">
        <span className="font-display text-[8px] uppercase tracking-widest text-muted-foreground/40">
          #
        </span>
        <span className="font-display text-[8px] uppercase tracking-widest text-muted-foreground/40">
          Team
        </span>
        <span className="text-right font-display text-[8px] uppercase tracking-widest text-muted-foreground/40">
          W-L
        </span>
        <span className="text-right font-display text-[8px] uppercase tracking-widest text-muted-foreground/40">
          PF
        </span>
      </div>

      <div className="divide-y divide-border">
        {data.standings.map((entry) => (
          <div
            key={entry.team_id}
            className="grid grid-cols-[20px_1fr_60px_80px] items-center gap-2 px-3 py-2.5 hover:bg-accent/30 transition-colors"
          >
            <span className="font-display text-xs font-bold text-muted-foreground/40">
              {entry.rank}
            </span>
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="shrink-0 text-muted-foreground/50">
                {entry.team_type?.toLowerCase() === "agent" ? (
                  <Bot className="h-3 w-3" />
                ) : (
                  <User className="h-3 w-3" />
                )}
              </span>
              <span className="truncate text-xs font-medium">{entry.team_name}</span>
            </div>
            <span className="text-right font-mono text-xs tabular-nums text-muted-foreground">
              {entry.wins}-{entry.losses}
              {entry.ties > 0 && `-${entry.ties}`}
            </span>
            <span className="text-right font-mono text-xs tabular-nums text-foreground">
              {entry.points_for.toFixed(1)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Decisions panel ──────────────────────────────────────────────────────────

const DECISION_TYPE_LABEL: Record<string, string> = {
  lineup: "Lineup",
  waiver: "Waiver",
  trade: "Trade",
  draft: "Draft",
};

function DecisionItem({ decision }: { decision: DecisionEntry }) {
  const [open, setOpen] = useState(false);
  const trace = decision.reasoning_trace;

  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-accent/30 transition-colors"
      >
        <div className="mt-0.5 shrink-0">
          <Brain className="h-3 w-3 text-muted-foreground/40" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-display text-[10px] font-semibold uppercase tracking-wide text-foreground">
              {DECISION_TYPE_LABEL[decision.decision_type] ?? decision.decision_type}
            </span>
            <span className="shrink-0 font-mono text-[9px] text-muted-foreground/40">
              #{decision.seq}
            </span>
          </div>
          <p className="truncate text-[10px] text-muted-foreground/60">{decision.team_name}</p>
          {trace?.summary && !open && (
            <p className="mt-0.5 line-clamp-2 text-[10px] leading-relaxed text-muted-foreground/50 italic">
              {trace.summary}
            </p>
          )}
        </div>
        {trace && (
          <ChevronRight
            className={cn(
              "mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/30 transition-transform",
              open && "rotate-90"
            )}
          />
        )}
      </button>

      {open && (
        <div className="border-t border-border/50 bg-muted/20 px-3 py-3 space-y-3">
          {/* Reasoning trace */}
          {trace?.summary && (
            <div>
              <p className="mb-1 font-display text-[8px] uppercase tracking-widest text-muted-foreground/50">
                Reasoning
              </p>
              <p className="text-[11px] leading-relaxed text-muted-foreground/80 whitespace-pre-wrap">
                {trace.summary}
              </p>
            </div>
          )}

          {/* Triggered by */}
          {decision.triggered_by.length > 0 && (
            <div>
              <p className="mb-1 font-display text-[8px] uppercase tracking-widest text-muted-foreground/50">
                Triggered by
              </p>
              <div className="flex flex-wrap gap-1">
                {decision.triggered_by.map((seq) => (
                  <span
                    key={seq}
                    className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground/60"
                  >
                    #{seq}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Payload */}
          <div>
            <p className="mb-1 font-display text-[8px] uppercase tracking-widest text-muted-foreground/50">
              Payload
            </p>
            <pre className="overflow-x-auto rounded-sm bg-card/60 p-2 font-mono text-[9px] leading-relaxed text-muted-foreground/60">
              {JSON.stringify(decision.payload, null, 2)}
            </pre>
          </div>

          {/* Tokens */}
          {decision.tokens_used > 0 && (
            <p className="font-mono text-[9px] text-muted-foreground/40">
              {decision.tokens_used.toLocaleString()} tokens
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DecisionsPanel({ data, loading }: { data: DecisionsResponse | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/40" />
        <p className="font-mono text-[9px] text-muted-foreground/40">loading decisions</p>
      </div>
    );
  }

  if (!data || data.decisions.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="font-display text-[10px] uppercase tracking-wider text-muted-foreground/40">
          No decisions yet
        </p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-border">
      {data.decisions.map((d) => (
        <DecisionItem key={d.id} decision={d} />
      ))}
    </div>
  );
}

// ─── Right panel ──────────────────────────────────────────────────────────────

type RightTab = "matchups" | "standings" | "decisions";

const RIGHT_TABS: { id: RightTab; label: string; icon: React.ReactNode }[] = [
  { id: "matchups", label: "Matchups", icon: <Swords className="h-3 w-3" /> },
  { id: "standings", label: "Standings", icon: <ListOrdered className="h-3 w-3" /> },
  { id: "decisions", label: "Decisions", icon: <Brain className="h-3 w-3" /> },
];

function RightPanel({
  leagueId,
  sessionId,
  scoresData,
  scoresLoading,
  standingsData,
  standingsLoading,
  decisionsData,
  decisionsLoading,
}: {
  leagueId: string;
  sessionId: string;
  scoresData: WeekScoresResponse | null;
  scoresLoading: boolean;
  standingsData: StandingsResponse | null;
  standingsLoading: boolean;
  decisionsData: DecisionsResponse | null;
  decisionsLoading: boolean;
}) {
  const [activeTab, setActiveTab] = useState<RightTab>("matchups");

  return (
    <div className="flex min-h-0 flex-col rounded-sm border border-border bg-card">
      {/* Tab strip */}
      <div className="flex border-b border-border">
        {RIGHT_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 border-b-2 px-2 py-2.5 font-display text-[9px] uppercase tracking-wider transition-colors",
              activeTab === tab.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground/50 hover:text-muted-foreground"
            )}
          >
            {tab.icon}
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content — scrollable */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "matchups" && (
          <MatchupsPanel scoresData={scoresData} loading={scoresLoading} />
        )}
        {activeTab === "standings" && (
          <StandingsPanel data={standingsData} loading={standingsLoading} />
        )}
        {activeTab === "decisions" && (
          <DecisionsPanel data={decisionsData} loading={decisionsLoading} />
        )}
      </div>

      {/* Actions footer */}
      <div className="border-t border-border">
        <div className="flex items-center gap-1 border-b border-border px-3 py-2">
          <BarChart3 className="h-3 w-3 text-muted-foreground/40" />
          <span className="font-display text-[9px] font-bold uppercase tracking-[0.15em] text-muted-foreground/60">
            Actions
          </span>
        </div>
        <div className="p-1.5">
          <Link
            to={`/leagues/${leagueId}/sessions/${sessionId}/lineup`}
            className="flex items-center justify-between rounded-sm px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <span className="font-display text-[10px] uppercase tracking-wider">Edit lineup</span>
            <ArrowLeft className="h-3 w-3 rotate-180" />
          </Link>
          <Link
            to={`/leagues/${leagueId}/sessions/${sessionId}/waivers`}
            className="flex items-center justify-between rounded-sm px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <span className="font-display text-[10px] uppercase tracking-wider">Waiver claims</span>
            <ArrowLeft className="h-3 w-3 rotate-180" />
          </Link>
          <Link
            to={`/leagues/${leagueId}/sessions/${sessionId}/trades`}
            className="flex items-center justify-between rounded-sm px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <span className="font-display text-[10px] uppercase tracking-wider">Trades</span>
            <ArrowLeft className="h-3 w-3 rotate-180" />
          </Link>
        </div>
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
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [actionPending, setActionPending] = useState(false);

  const [league, setLeague] = useState<League | null>(null);
  const [leagueSessions, setLeagueSessions] = useState<SessionSummary[]>([]);

  // Right-panel data
  const [scoresData, setScoresData] = useState<WeekScoresResponse | null>(null);
  const [scoresLoading, setScoresLoading] = useState(false);
  const [standingsData, setStandingsData] = useState<StandingsResponse | null>(null);
  const [standingsLoading, setStandingsLoading] = useState(false);
  const [decisionsData, setDecisionsData] = useState<DecisionsResponse | null>(null);
  const [decisionsLoading, setDecisionsLoading] = useState(false);

  // Load session details
  useEffect(() => {
    if (!sessionId) return;
    api
      .GET("/sessions/{session_id}", { params: { path: { session_id: sessionId } } })
      .then(({ data }) => {
        if (data) setSessionDetail(data);
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

  // Fetch scores
  const fetchScores = useCallback(async () => {
    if (!sessionId) return;
    setScoresLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await (api as any).GET(`/sessions/${sessionId}/scores`);
      if (res.data) setScoresData(res.data as WeekScoresResponse);
    } catch {
      // silently ignore
    } finally {
      setScoresLoading(false);
    }
  }, [sessionId]);

  // Fetch standings
  const fetchStandings = useCallback(async () => {
    if (!sessionId) return;
    setStandingsLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await (api as any).GET(`/sessions/${sessionId}/standings`);
      if (res.data) setStandingsData(res.data as StandingsResponse);
    } catch {
      // silently ignore
    } finally {
      setStandingsLoading(false);
    }
  }, [sessionId]);

  // Fetch decisions
  const fetchDecisions = useCallback(async () => {
    if (!sessionId) return;
    setDecisionsLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await (api as any).GET(`/sessions/${sessionId}/decisions`);
      if (res.data) setDecisionsData(res.data as DecisionsResponse);
    } catch {
      // silently ignore
    } finally {
      setDecisionsLoading(false);
    }
  }, [sessionId]);

  // Initial load of right-panel data
  useEffect(() => {
    fetchScores();
    fetchStandings();
    fetchDecisions();
  }, [fetchScores, fetchStandings, fetchDecisions]);

  // Polling: refresh right-panel data every 10s when running
  useEffect(() => {
    if (!sessionDetail?.is_running) return;
    const id = setInterval(() => {
      fetchScores();
      fetchStandings();
      fetchDecisions();
    }, 10_000);
    return () => clearInterval(id);
  }, [sessionDetail?.is_running, fetchScores, fetchStandings, fetchDecisions]);

  const handleEvent = useCallback(
    (ev: SessionEvent) => {
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

      // Eagerly refresh data panels on relevant events
      if (
        ev.type === "SCORE_UPDATE" ||
        ev.type === "WEEK_END" ||
        ev.type === "WAIVER_RESOLVED" ||
        ev.type === "TRADE_RESOLVED"
      ) {
        fetchScores();
        if (ev.type === "WEEK_END") {
          fetchStandings();
        }
      }
      if (
        ev.type === "AGENT_WINDOW_CLOSE" ||
        ev.type === "REACTION_WINDOW_CLOSE" ||
        ev.type === "WEEK_END"
      ) {
        fetchDecisions();
      }
    },
    [fetchScores, fetchStandings, fetchDecisions]
  );

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
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1fr_320px]">
          <EventLog events={events} />

          <RightPanel
            leagueId={leagueId}
            sessionId={sessionId}
            scoresData={scoresData}
            scoresLoading={scoresLoading}
            standingsData={standingsData}
            standingsLoading={standingsLoading}
            decisionsData={decisionsData}
            decisionsLoading={decisionsLoading}
          />
        </div>
      </div>
    </div>
  );
}
