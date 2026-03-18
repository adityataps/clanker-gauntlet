import { createPortal } from "react-dom";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Layers,
  Users,
  Settings,
  Crown,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { components } from "@/api/schema";

type League = components["schemas"]["LeagueResponse"];
type Session = components["schemas"]["SessionResponse"];

export type SidebarActiveView = "sessions" | "members" | "settings";

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_DOT_CLS: Record<string, string> = {
  draft_pending: "bg-muted-foreground/40",
  draft_in_progress: "bg-sky-400",
  in_progress: "bg-primary",
  paused: "bg-amber-400",
  completed: "bg-muted-foreground/30",
};

const STATUS_LABEL: Record<string, string> = {
  draft_pending: "Setup",
  draft_in_progress: "Draft",
  in_progress: "Playing",
  paused: "Paused",
  completed: "Done",
};

const SPEED_EMOJI: Record<string, string> = {
  blitz: "⚡",
  managed: "⏱️",
  immersive: "🐌",
};

// Icon tints for the collapsed rail
const STATUS_ICON_CLS: Record<string, string> = {
  in_progress: "border-primary/50 text-primary bg-primary/10",
  paused: "border-amber-400/50 text-amber-300 bg-amber-400/10",
  draft_in_progress: "border-sky-400/50 text-sky-400 bg-sky-400/10",
  draft_pending: "border-border text-muted-foreground bg-card",
  completed: "border-border text-muted-foreground/40 bg-card",
};

const SESSION_GROUPS = [
  {
    key: "live",
    label: "Live",
    filter: (s: Session) => s.status === "in_progress" && s.script_speed === "immersive",
  },
  {
    key: "running",
    label: "Playing",
    filter: (s: Session) => s.status === "in_progress" && s.script_speed !== "immersive",
  },
  { key: "paused", label: "Paused", filter: (s: Session) => s.status === "paused" },
  {
    key: "setup",
    label: "Setup",
    filter: (s: Session) => s.status === "draft_pending" || s.status === "draft_in_progress",
  },
  { key: "done", label: "Done", filter: (s: Session) => s.status === "completed" },
];

const LS_KEY = "cg:sidebar-open";

function readStorage(): boolean {
  try {
    return localStorage.getItem(LS_KEY) !== "false";
  } catch {
    return true;
  }
}

function writeStorage(value: boolean) {
  try {
    localStorage.setItem(LS_KEY, String(value));
  } catch {
    // ignore
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

export function StatusDot({ status }: { status: string }) {
  const key = status.toLowerCase();
  const isLive = key === "in_progress";
  return (
    <span className="relative flex h-2 w-2 shrink-0 items-center justify-center">
      {isLive && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-50" />
      )}
      <span
        className={cn(
          "relative inline-flex h-1.5 w-1.5 rounded-full",
          STATUS_DOT_CLS[key] ?? "bg-muted-foreground/40"
        )}
      />
    </span>
  );
}

function TooltipRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="font-display text-[9px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-[10px] capitalize text-foreground">{value}</span>
    </div>
  );
}

function SessionTooltip({ session, x, y }: { session: Session; x: number; y: number }) {
  const left = Math.min(x + 16, window.innerWidth - 224);
  const top = y + 12;
  return createPortal(
    <div
      className="pointer-events-none fixed z-[9999] w-52 rounded-sm border border-border bg-card p-3 shadow-xl"
      style={{ left, top }}
    >
      <p className="mb-2 truncate font-display text-xs font-bold uppercase tracking-wide text-foreground">
        {session.name}
      </p>
      <div className="space-y-1.5">
        <TooltipRow label="Sport" value={`${session.sport.toUpperCase()} ${session.season}`} />
        <TooltipRow
          label="Speed"
          value={`${SPEED_EMOJI[session.script_speed] ?? ""} ${session.script_speed}`}
        />
        <TooltipRow label="Waiver" value={session.waiver_mode} />
        <TooltipRow label="Teams" value={`${session.current_teams} / ${session.max_teams}`} />
        {session.current_week > 0 && <TooltipRow label="Week" value={`${session.current_week}`} />}
        <TooltipRow
          label="Status"
          value={STATUS_LABEL[session.status.toLowerCase()] ?? session.status}
        />
      </div>
    </div>,
    document.body
  );
}

// Full-width row used in the expanded sidebar
function SessionRow({
  session,
  leagueId,
  isActive,
}: {
  session: Session;
  leagueId: string;
  isActive: boolean;
}) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  return (
    <div
      onMouseMove={(e) => {
        if (leaveTimer.current) clearTimeout(leaveTimer.current);
        setPos({ x: e.clientX, y: e.clientY });
      }}
      onMouseLeave={() => {
        leaveTimer.current = setTimeout(() => setPos(null), 80);
      }}
    >
      <Link
        to={`/leagues/${leagueId}/sessions/${session.id}`}
        className={cn(
          "flex items-center gap-2 border-l-2 px-2 py-2 text-[11px] transition-colors hover:bg-accent hover:text-foreground",
          isActive
            ? "border-l-primary bg-accent/60 text-foreground"
            : "border-l-transparent text-muted-foreground"
        )}
      >
        <StatusDot status={session.status} />
        <span className="flex-1 truncate font-medium">{session.name}</span>
        <span className="font-display text-[8px] tracking-wider text-muted-foreground/50">
          {SPEED_EMOJI[session.script_speed] ?? ""}
        </span>
      </Link>
      {pos && <SessionTooltip session={session} x={pos.x} y={pos.y} />}
    </div>
  );
}

// Icon pin used in the collapsed rail
function SessionIconPin({
  session,
  leagueId,
  isActive,
}: {
  session: Session;
  leagueId: string;
  isActive: boolean;
}) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const initial = (session.name.trim().charAt(0) || "?").toUpperCase();
  const iconCls = STATUS_ICON_CLS[session.status] ?? STATUS_ICON_CLS.draft_pending;

  return (
    <div
      onMouseMove={(e) => {
        if (leaveTimer.current) clearTimeout(leaveTimer.current);
        setPos({ x: e.clientX, y: e.clientY });
      }}
      onMouseLeave={() => {
        leaveTimer.current = setTimeout(() => setPos(null), 80);
      }}
    >
      <Link
        to={`/leagues/${leagueId}/sessions/${session.id}`}
        className={cn(
          "relative flex h-8 w-8 items-center justify-center rounded-sm border transition-colors",
          isActive
            ? "border-primary bg-primary/20 text-primary"
            : cn(iconCls, "hover:border-primary/40 hover:bg-accent")
        )}
        title={session.name}
      >
        <span className="font-display text-xs font-bold leading-none">{initial}</span>
        {/* Status dot — top-right corner */}
        <span className="absolute -right-0.5 -top-0.5 flex h-2 w-2 items-center justify-center">
          <StatusDot status={session.status} />
        </span>
      </Link>
      {pos && <SessionTooltip session={session} x={pos.x} y={pos.y} />}
    </div>
  );
}

// ─── LeagueSidebar ────────────────────────────────────────────────────────────

export interface LeagueSidebarProps {
  league: League;
  sessions: Session[];
  /** Highlighted session row (Session page only) */
  activeSessionId?: string;
  /** Highlighted bottom-nav item */
  activeView?: SidebarActiveView;
  onNavigateSessions: () => void;
  onNavigateMembers: () => void;
  /** Pass undefined to hide the Settings item (non-managers) */
  onNavigateSettings?: () => void;
  canCreate?: boolean;
  onCreateSession?: () => void;
  onBack: () => void;
  backLabel?: string;
  /** Rendered below the bottom nav — use for page-specific actions like "Leave league" */
  footer?: React.ReactNode;
  memberCount?: number;
}

export function LeagueSidebar({
  league,
  sessions,
  activeSessionId,
  activeView,
  onNavigateSessions,
  onNavigateMembers,
  onNavigateSettings,
  canCreate,
  onCreateSession,
  onBack,
  backLabel = "Dashboard",
  footer,
  memberCount,
}: LeagueSidebarProps) {
  // Sidebar open state is self-managed and persisted to localStorage
  const [open, setOpen] = useState(readStorage);

  function toggle() {
    const next = !open;
    setOpen(next);
    writeStorage(next);
  }

  const grouped = SESSION_GROUPS.map((g) => ({
    ...g,
    items: sessions.filter(g.filter),
  })).filter((g) => g.items.length > 0);

  const iconNavCls = cn(
    "flex h-7 w-7 items-center justify-center rounded-sm transition-colors",
    "text-muted-foreground hover:bg-accent hover:text-foreground"
  );
  const iconNavActiveCls = "bg-accent text-foreground";

  return (
    <aside
      className="flex shrink-0 flex-col overflow-hidden border-r border-border bg-card"
      style={{ width: open ? "256px" : "44px", transition: "width 200ms ease" }}
    >
      {open ? (
        /* ── Expanded sidebar ─────────────────────────────────────────────── */
        <div className="flex w-64 flex-1 flex-col overflow-y-auto">
          {/* Back + collapse */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <button
              className="flex items-center gap-1.5 font-display text-[10px] uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
              onClick={onBack}
            >
              <ArrowLeft className="h-3 w-3" />
              {backLabel}
            </button>
            <button
              onClick={toggle}
              className="flex h-5 w-5 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              title="Collapse sidebar"
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
          </div>

          {/* League identity */}
          <div className="border-b border-border px-4 py-4">
            <h1 className="font-display text-base font-bold uppercase tracking-wide leading-tight text-foreground">
              {league.name}
            </h1>
            {league.my_role && (
              <div className="mt-1 flex items-center gap-1">
                {league.my_role === "manager" && <Crown className="h-2.5 w-2.5 text-primary" />}
                <span className="font-display text-[10px] uppercase tracking-wider text-muted-foreground">
                  {league.my_role}
                </span>
              </div>
            )}
          </div>

          {/* Sessions list */}
          <div className="flex-1 px-2 py-3">
            <div className="mb-1 flex items-center justify-between px-2">
              <span className="font-display text-[9px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Sessions
              </span>
              {canCreate && onCreateSession && (
                <button
                  onClick={onCreateSession}
                  className="flex h-5 w-5 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  title="New session"
                >
                  <Plus className="h-3 w-3" />
                </button>
              )}
            </div>

            {sessions.length === 0 ? (
              <div className="px-2 py-3">
                <p className="text-[11px] text-muted-foreground/60">No sessions yet.</p>
                {canCreate && onCreateSession && (
                  <button
                    onClick={onCreateSession}
                    className="mt-1 font-display text-[10px] uppercase tracking-wider text-primary hover:underline"
                  >
                    Create one →
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {grouped.map((group) => (
                  <div key={group.key}>
                    <div className="mb-0.5 flex items-center gap-1.5 px-2">
                      <span className="font-display text-[8px] uppercase tracking-[0.2em] text-muted-foreground/50">
                        {group.label}
                      </span>
                      <div className="h-px flex-1 bg-border/40" />
                    </div>
                    <div className="space-y-0.5">
                      {group.items.map((s) => (
                        <SessionRow
                          key={s.id}
                          session={s}
                          leagueId={league.id}
                          isActive={s.id === activeSessionId}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Bottom nav */}
          <div className="border-t border-border px-2 py-2">
            <button
              onClick={onNavigateSessions}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-sm px-2 py-2 font-display text-xs uppercase tracking-wider transition-colors",
                activeView === "sessions"
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <Layers className="h-3.5 w-3.5" />
              Sessions
              <span className="ml-auto font-mono text-[10px] tabular-nums opacity-60">
                {sessions.length}
              </span>
            </button>
            <button
              onClick={onNavigateMembers}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-sm px-2 py-2 font-display text-xs uppercase tracking-wider transition-colors",
                activeView === "members"
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <Users className="h-3.5 w-3.5" />
              Members
              {memberCount != null && (
                <span className="ml-auto font-mono text-[10px] tabular-nums opacity-60">
                  {memberCount}
                </span>
              )}
            </button>
            {onNavigateSettings && (
              <button
                onClick={onNavigateSettings}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-sm px-2 py-2 font-display text-xs uppercase tracking-wider transition-colors",
                  activeView === "settings"
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                <Settings className="h-3.5 w-3.5" />
                Settings
              </button>
            )}
          </div>

          {footer}
        </div>
      ) : (
        /* ── Collapsed icon rail ──────────────────────────────────────────── */
        <div className="flex w-11 flex-1 flex-col items-center gap-2 py-3">
          {/* Expand button */}
          <button
            onClick={toggle}
            className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="Expand sidebar"
          >
            <ChevronRight className="h-3 w-3" />
          </button>

          {/* Session icon pins — scrollable */}
          <div className="flex flex-1 flex-col items-center gap-1.5 overflow-y-auto py-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {sessions.map((s) => (
              <SessionIconPin
                key={s.id}
                session={s}
                leagueId={league.id}
                isActive={s.id === activeSessionId}
              />
            ))}
          </div>

          {/* Bottom nav icons */}
          <div className="flex flex-col items-center gap-0.5 border-t border-border pt-2">
            <button
              onClick={onNavigateSessions}
              className={cn(iconNavCls, activeView === "sessions" && iconNavActiveCls)}
              title="Sessions"
            >
              <Layers className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={onNavigateMembers}
              className={cn(iconNavCls, activeView === "members" && iconNavActiveCls)}
              title="Members"
            >
              <Users className="h-3.5 w-3.5" />
            </button>
            {onNavigateSettings && (
              <button
                onClick={onNavigateSettings}
                className={cn(iconNavCls, activeView === "settings" && iconNavActiveCls)}
                title="Settings"
              >
                <Settings className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
