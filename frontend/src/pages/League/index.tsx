import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Plus,
  Copy,
  Check,
  UserMinus,
  Crown,
  Users,
  Layers,
  MoreHorizontal,
  Loader2,
  Eye,
  EyeOff,
  Save,
  Trash2,
  Settings,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { api } from "@/api/client";
import { useAuthStore } from "@/store/authStore";
import type { components } from "@/api/schema";

type League = components["schemas"]["LeagueResponse"];
type Member = components["schemas"]["MemberResponse"];
type Session = components["schemas"]["SessionResponse"];
type Invite = components["schemas"]["InviteResponse"];

type ActiveView = "sessions" | "members" | "settings";

// ─── Session status helpers ────────────────────────────────────────────────────

const STATUS_DOT: Record<string, string> = {
  draft_pending: "bg-muted-foreground/40",
  draft_in_progress: "bg-sky-400",
  in_progress: "bg-primary",
  paused: "bg-amber-400",
  completed: "bg-muted-foreground/30",
};

const STATUS_LABEL: Record<string, string> = {
  draft_pending: "Setup",
  draft_in_progress: "Draft",
  in_progress: "Live",
  paused: "Paused",
  completed: "Done",
};

function StatusDot({ status }: { status: string }) {
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
          STATUS_DOT[key] ?? "bg-muted-foreground/40"
        )}
      />
    </span>
  );
}

function SessionStatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();
  const label = STATUS_LABEL[key] ?? key.replace(/_/g, " ");
  const cls: Record<string, string> = {
    draft_pending: "border-border text-muted-foreground",
    draft_in_progress: "border-sky-500/30 text-sky-400",
    in_progress: "border-primary/30 text-primary",
    paused: "border-amber-500/30 text-amber-400",
    completed: "border-border text-muted-foreground",
  };
  return (
    <span
      className={cn(
        "rounded-sm border px-1.5 py-0.5 font-display text-[9px] font-semibold uppercase tracking-wider",
        cls[key] ?? "border-border text-muted-foreground"
      )}
    >
      {label}
    </span>
  );
}

// ─── Speed emoji ──────────────────────────────────────────────────────────────

const SPEED_EMOJI: Record<string, string> = {
  blitz: "⚡",
  managed: "🕐",
  immersive: "🌐",
};

// ─── Session hover card ────────────────────────────────────────────────────────

function SessionHoverCard({ session }: { session: Session }) {
  return (
    <div className="pointer-events-none absolute left-[calc(100%+8px)] top-0 z-50 w-52 rounded-sm border border-border bg-card p-3 shadow-lg">
      <p className="mb-2 truncate font-display text-xs font-bold uppercase tracking-wide text-foreground">
        {session.name}
      </p>
      <div className="space-y-1.5">
        <Row label="Sport" value={`${session.sport.toUpperCase()} ${session.season}`} />
        <Row
          label="Speed"
          value={`${SPEED_EMOJI[session.script_speed] ?? ""} ${session.script_speed}`}
        />
        <Row label="Waiver" value={session.waiver_mode} />
        <Row label="Teams" value={`${session.current_teams} / ${session.max_teams}`} />
        <Row label="Status" value={STATUS_LABEL[session.status.toLowerCase()] ?? session.status} />
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="font-display text-[9px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-[10px] capitalize text-foreground">{value}</span>
    </div>
  );
}

// ─── Script helpers ────────────────────────────────────────────────────────────

type ScriptOption = components["schemas"]["ScriptResponse"];

function scriptLabel(s: ScriptOption) {
  return `${s.sport.toUpperCase()} ${s.season} — ${s.season_type} (${s.total_events} events)`;
}

// ─── Create session dialog ────────────────────────────────────────────────────

function CreateSessionDialog({
  leagueId,
  open,
  onOpenChange,
  onCreated,
}: {
  leagueId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: (s: Session) => void;
}) {
  const [name, setName] = useState("");
  const [scriptSpeed, setScriptSpeed] = useState("blitz");
  const [maxTeams, setMaxTeams] = useState("10");
  const [scripts, setScripts] = useState<ScriptOption[]>([]);
  const [scriptId, setScriptId] = useState("");
  const [scriptsLoading, setScriptsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setScriptsLoading(true);
    api
      .GET("/scripts")
      .then(({ data }) => {
        const list = data ?? [];
        setScripts(list);
        if (list.length > 0 && !scriptId) setScriptId(list[0].id);
      })
      .finally(() => setScriptsLoading(false));
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedScript = scripts.find((s) => s.id === scriptId) ?? null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedScript) return;
    setError(null);
    setSaving(true);
    try {
      const { data, error: apiError } = await api.POST("/leagues/{league_id}/sessions", {
        params: { path: { league_id: leagueId } },
        body: {
          name: name.trim(),
          script_id: selectedScript.id,
          sport: selectedScript.sport,
          season: selectedScript.season,
          script_speed: scriptSpeed,
          max_teams: parseInt(maxTeams, 10),
        },
      });
      if (apiError || !data) throw new Error("Failed to create session");
      onCreated(data);
      onOpenChange(false);
      setName("");
    } catch {
      setError("Failed to create session.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New session</DialogTitle>
          <DialogDescription>
            Configure and launch a new simulation session for this league.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="session-name">Session name</Label>
            <Input
              id="session-name"
              placeholder="2025 Season Replay"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label>Season script</Label>
            {scriptsLoading ? (
              <div className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading scripts…
              </div>
            ) : scripts.length === 0 ? (
              <p className="text-sm text-destructive">
                No compiled scripts found. Run the ScriptCompiler first.
              </p>
            ) : (
              <Select value={scriptId} onValueChange={setScriptId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {scripts.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {scriptLabel(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Script speed</Label>
            <Select value={scriptSpeed} onValueChange={setScriptSpeed}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="blitz">Blitz — as fast as possible</SelectItem>
                <SelectItem value="managed">Managed — compressed wall-clock</SelectItem>
                <SelectItem value="immersive">Immersive — 1:1 real time</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="max-teams">Max teams</Label>
            <Input
              id="max-teams"
              type="number"
              min={2}
              max={20}
              value={maxTeams}
              onChange={(e) => setMaxTeams(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || !selectedScript || saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Create session
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Invite dialog ────────────────────────────────────────────────────────────

function InviteDialog({
  league,
  open,
  onOpenChange,
}: {
  league: League;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [invite, setInvite] = useState<Invite | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .POST("/leagues/{league_id}/invites", {
        params: { path: { league_id: league.id } },
      })
      .then(({ data }) => setInvite(data ?? null))
      .finally(() => setLoading(false));
  }, [open, league.id]);

  const inviteUrl = invite ? `${window.location.origin}/join/${invite.token}` : "";

  async function handleCopy() {
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Invite member</DialogTitle>
          <DialogDescription>
            Share this link to invite someone to <strong>{league.name}</strong>. Expires in 72
            hours.
          </DialogDescription>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : invite ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input value={inviteUrl} readOnly className="text-xs" />
              <Button size="sm" variant="outline" onClick={handleCopy} className="shrink-0">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Expires{" "}
              {new Date(invite.expires_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>
        ) : (
          <p className="text-sm text-destructive">Failed to generate invite link.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Members panel ────────────────────────────────────────────────────────────

function MembersPanel({
  league,
  members,
  isManager,
  onRefresh,
}: {
  league: League;
  members: Member[];
  isManager: boolean;
  onRefresh: () => void;
}) {
  const { user } = useAuthStore();
  const [inviteOpen, setInviteOpen] = useState(false);

  async function handlePromote(memberId: string) {
    await api.PATCH("/leagues/{league_id}/members/{user_id}", {
      params: { path: { league_id: league.id, user_id: memberId } },
      body: { role: "manager" },
    });
    onRefresh();
  }

  async function handleRemove(memberId: string) {
    await api.DELETE("/leagues/{league_id}/members/{user_id}", {
      params: { path: { league_id: league.id, user_id: memberId } },
    });
    onRefresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-lg font-bold uppercase tracking-wide">Members</h2>
          <p className="text-xs text-muted-foreground">
            {members.length} {members.length === 1 ? "member" : "members"}
          </p>
        </div>
        {isManager && (
          <Button
            size="sm"
            variant="outline"
            className="rounded-sm font-display text-xs uppercase tracking-wide"
            onClick={() => setInviteOpen(true)}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Invite
          </Button>
        )}
      </div>

      <div className="divide-y divide-border rounded-sm border border-border">
        {members.map((m) => (
          <div key={m.user_id} className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent font-display text-xs font-bold uppercase text-muted-foreground">
                {m.display_name?.[0] ?? "?"}
              </div>
              <div>
                <p className="text-sm font-medium">{m.display_name}</p>
                <p className="text-xs text-muted-foreground">{m.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 font-display text-[9px] uppercase tracking-wider text-muted-foreground">
                {m.role === "manager" && <Crown className="h-2.5 w-2.5" />}
                {m.role}
              </span>
              {isManager && m.user_id !== user?.id && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-7 w-7">
                      <MoreHorizontal className="h-3.5 w-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-40">
                    {m.role !== "manager" && (
                      <DropdownMenuItem onClick={() => handlePromote(m.user_id)}>
                        <Crown className="mr-2 h-3.5 w-3.5" />
                        Make manager
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => handleRemove(m.user_id)}
                      className="text-destructive focus:text-destructive"
                    >
                      <UserMinus className="mr-2 h-3.5 w-3.5" />
                      Remove
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
        ))}
      </div>

      <InviteDialog league={league} open={inviteOpen} onOpenChange={setInviteOpen} />
    </div>
  );
}

// ─── Settings panel ───────────────────────────────────────────────────────────

const PROVIDERS = [
  { key: "anthropic", label: "Anthropic (Claude)" },
  { key: "openai", label: "OpenAI (GPT)" },
  { key: "gemini", label: "Google (Gemini)" },
] as const;

type ProviderKey = (typeof PROVIDERS)[number]["key"];

function LeagueApiKeyRow({
  leagueId,
  providerKey,
  label,
  hasKey,
  onSaved,
}: {
  leagueId: string;
  providerKey: ProviderKey;
  label: string;
  hasKey: boolean;
  onSaved: () => void;
}) {
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleSave() {
    if (!value.trim()) return;
    setSaving(true);
    try {
      await api.PUT("/leagues/{league_id}/api-key", {
        params: { path: { league_id: leagueId } },
        body: { provider: providerKey, api_key: value.trim() },
      });
      setValue("");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await api.DELETE("/leagues/{league_id}/api-key", {
        params: { path: { league_id: leagueId } },
        body: { provider: providerKey },
      });
      onSaved();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        {hasKey ? (
          <Badge variant="secondary" className="text-xs">
            Key saved
          </Badge>
        ) : (
          <Badge variant="outline" className="text-xs text-muted-foreground">
            Not set
          </Badge>
        )}
      </div>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            type={visible ? "text" : "password"}
            placeholder={hasKey ? "Enter new key to replace…" : "sk-…"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="pr-9"
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <Button size="sm" onClick={handleSave} disabled={!value.trim() || saving}>
          <Save className="mr-1.5 h-3.5 w-3.5" />
          {saving ? "Saving…" : "Save"}
        </Button>
        {hasKey && (
          <Button size="sm" variant="destructive" onClick={handleDelete} disabled={deleting}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

function SettingsPanel({
  league,
  onLeagueUpdated,
}: {
  league: League;
  onLeagueUpdated: (updated: Partial<League>) => void;
}) {
  const [hasKeys, setHasKeys] = useState<Record<string, boolean>>(league.has_league_keys ?? {});
  const [allowSharedKey, setAllowSharedKey] = useState(league.allow_shared_key);
  const [saving, setSaving] = useState(false);

  async function handleToggleSharedKey(enabled: boolean) {
    setAllowSharedKey(enabled);
    setSaving(true);
    try {
      await api.PATCH("/leagues/{league_id}", {
        params: { path: { league_id: league.id } },
        body: { allow_shared_key: enabled },
      });
      onLeagueUpdated({ allow_shared_key: enabled });
    } finally {
      setSaving(false);
    }
  }

  async function reloadKeys() {
    const { data } = await api.GET("/leagues/{league_id}/api-key", {
      params: { path: { league_id: league.id } },
    });
    if (data) setHasKeys(data.has_keys);
  }

  return (
    <div className="space-y-6">
      <h2 className="font-display text-lg font-bold uppercase tracking-wide">Settings</h2>

      <div className="flex items-start justify-between gap-4 rounded-sm border border-border p-4">
        <div>
          <p className="text-sm font-medium">League shared API key</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            When enabled, members without their own LLM key fall back to the league-level key.
          </p>
        </div>
        <Switch
          checked={allowSharedKey}
          onCheckedChange={handleToggleSharedKey}
          disabled={saving}
          aria-label="Toggle league shared key"
        />
      </div>

      {allowSharedKey && (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium">Provider keys</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Keys are encrypted at rest. All members' agent decisions share these rate limits.
            </p>
          </div>
          <Separator />
          {PROVIDERS.map(({ key, label }) => (
            <LeagueApiKeyRow
              key={key}
              leagueId={league.id}
              providerKey={key}
              label={label}
              hasKey={hasKeys[key] ?? false}
              onSaved={reloadKeys}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Sessions panel ───────────────────────────────────────────────────────────

function SessionsPanel({
  league,
  sessions,
  onNewSession,
  canCreate,
}: {
  league: League;
  sessions: Session[];
  onNewSession: () => void;
  canCreate: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-lg font-bold uppercase tracking-wide">Sessions</h2>
          <p className="text-xs text-muted-foreground">
            {sessions.length} {sessions.length === 1 ? "session" : "sessions"}
          </p>
        </div>
        {canCreate && (
          <Button
            size="sm"
            className="rounded-sm font-display text-xs font-bold uppercase tracking-[0.1em]"
            onClick={onNewSession}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            New session
          </Button>
        )}
      </div>

      {sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-sm border border-dashed border-border py-20 text-center">
          <Layers className="mb-3 h-8 w-8 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">No sessions yet.</p>
          {canCreate && (
            <Button
              variant="outline"
              size="sm"
              className="mt-4 rounded-sm font-display text-xs uppercase tracking-wide"
              onClick={onNewSession}
            >
              Create the first session
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {sessions.map((s) => (
            <Link
              key={s.id}
              to={`/leagues/${league.id}/sessions/${s.id}`}
              className="group flex items-center justify-between rounded-sm border border-border bg-card px-4 py-3 transition-all hover:border-primary/30 hover:bg-accent"
            >
              <div>
                <div className="flex items-center gap-2">
                  <StatusDot status={s.status} />
                  <p className="font-medium">{s.name}</p>
                </div>
                <p className="mt-0.5 pl-4 font-mono text-[10px] text-muted-foreground">
                  {SPEED_EMOJI[s.script_speed] ?? ""} {s.script_speed.toUpperCase()} ·{" "}
                  {s.sport.toUpperCase()} {s.season} · {s.current_teams}/{s.max_teams} teams
                </p>
              </div>
              <div className="flex items-center gap-2">
                <SessionStatusBadge status={s.status} />
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export function LeaguePage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();

  const [league, setLeague] = useState<League | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<ActiveView>("sessions");
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    if (!leagueId) return;
    const [leagueRes, membersRes, sessionsRes] = await Promise.all([
      api.GET("/leagues/{league_id}", { params: { path: { league_id: leagueId } } }),
      api.GET("/leagues/{league_id}/members", { params: { path: { league_id: leagueId } } }),
      api.GET("/leagues/{league_id}/sessions", { params: { path: { league_id: leagueId } } }),
    ]);
    setLeague(leagueRes.data ?? null);
    setMembers(membersRes.data ?? []);
    setSessions(sessionsRes.data ?? []);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, [leagueId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!league) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <p className="text-muted-foreground">League not found.</p>
        <Button variant="outline" onClick={() => navigate("/dashboard")}>
          Go to dashboard
        </Button>
      </div>
    );
  }

  const isManager = league.my_role === "manager";
  const isMember = !!league.my_role;
  const canCreate = isManager || (isMember && league.session_creation === "any_member");

  return (
    <div className="flex" style={{ height: "calc(100vh - 48px)" }}>
      {/* ── Sidebar ──────────────────────────────────────────────────────────── */}
      <aside className="flex w-64 shrink-0 flex-col overflow-y-auto border-r border-border bg-card">
        {/* Back */}
        <div className="border-b border-border px-4 py-3">
          <button
            className="flex items-center gap-1.5 font-display text-[10px] uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => navigate("/dashboard")}
          >
            <ArrowLeft className="h-3 w-3" />
            Dashboard
          </button>
        </div>

        {/* League identity */}
        <div className="border-b border-border px-4 py-4">
          <h1 className="font-display text-base font-bold uppercase tracking-wide leading-tight text-foreground">
            {league.name}
          </h1>
          {league.my_role && (
            <div className="mt-1 flex items-center gap-1">
              {isManager && <Crown className="h-2.5 w-2.5 text-primary" />}
              <span className="font-display text-[10px] uppercase tracking-wider text-muted-foreground">
                {league.my_role}
              </span>
            </div>
          )}
        </div>

        {/* Sessions section */}
        <div className="flex-1 px-2 py-3">
          <div className="mb-1 flex items-center justify-between px-2">
            <span className="font-display text-[9px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Sessions
            </span>
            {canCreate && (
              <button
                onClick={() => setCreateOpen(true)}
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
              {canCreate && (
                <button
                  onClick={() => setCreateOpen(true)}
                  className="mt-1 font-display text-[10px] uppercase tracking-wider text-primary hover:underline"
                >
                  Create one →
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-0.5">
              {sessions.map((s) => (
                <div key={s.id} className="group/session relative">
                  <Link
                    to={`/leagues/${league.id}/sessions/${s.id}`}
                    className="flex items-center gap-2 rounded-sm px-2 py-2 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    <StatusDot status={s.status} />
                    <span className="flex-1 truncate font-medium">{s.name}</span>
                    <span className="font-display text-[8px] uppercase tracking-wider opacity-60">
                      {SPEED_EMOJI[s.script_speed] ?? ""}{" "}
                      {STATUS_LABEL[s.status.toLowerCase()] ?? s.status}
                    </span>
                  </Link>
                  <div className="invisible opacity-0 transition-all duration-150 group-hover/session:visible group-hover/session:opacity-100">
                    <SessionHoverCard session={s} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Nav items */}
        <div className="border-t border-border px-2 py-2">
          <button
            onClick={() => setActiveView("sessions")}
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
            onClick={() => setActiveView("members")}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-sm px-2 py-2 font-display text-xs uppercase tracking-wider transition-colors",
              activeView === "members"
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Users className="h-3.5 w-3.5" />
            Members
            <span className="ml-auto font-mono text-[10px] tabular-nums opacity-60">
              {members.length}
            </span>
          </button>
          {isManager && (
            <button
              onClick={() => setActiveView("settings")}
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

        {/* Leave league */}
        {isMember && !isManager && (
          <div className="border-t border-border px-2 py-2">
            <button
              className="w-full rounded-sm px-2 py-2 text-left font-display text-[10px] uppercase tracking-wider text-destructive/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
              onClick={async () => {
                if (!leagueId) return;
                await api.POST("/leagues/{league_id}/members/me/leave", {
                  params: { path: { league_id: leagueId } },
                });
                navigate("/dashboard");
              }}
            >
              Leave league
            </button>
          </div>
        )}
      </aside>

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto px-8 py-8">
        {activeView === "sessions" && (
          <SessionsPanel
            league={league}
            sessions={sessions}
            onNewSession={() => setCreateOpen(true)}
            canCreate={canCreate}
          />
        )}
        {activeView === "members" && (
          <MembersPanel
            league={league}
            members={members}
            isManager={isManager}
            onRefresh={() => {
              if (!leagueId) return;
              api
                .GET("/leagues/{league_id}/members", {
                  params: { path: { league_id: leagueId } },
                })
                .then(({ data }) => setMembers(data ?? []));
            }}
          />
        )}
        {activeView === "settings" && isManager && (
          <SettingsPanel
            league={league}
            onLeagueUpdated={(updated) =>
              setLeague((prev) => (prev ? { ...prev, ...updated } : prev))
            }
          />
        )}
      </main>

      {/* ── Dialogs ──────────────────────────────────────────────────────────── */}
      <CreateSessionDialog
        leagueId={league.id}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(s) => {
          setSessions((prev) => [s, ...prev]);
        }}
      />
    </div>
  );
}
