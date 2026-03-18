import { useEffect, useState } from "react";
import { Link, useParams, useNavigate, useLocation } from "react-router-dom";
import {
  Plus,
  Copy,
  Check,
  UserMinus,
  MoreHorizontal,
  Loader2,
  Eye,
  EyeOff,
  Save,
  Trash2,
  Play,
  Pause,
  Crown,
  Layers,
} from "lucide-react";
import { LeagueSidebar, StatusDot } from "@/components/LeagueSidebar";
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

const STATUS_LABEL: Record<string, string> = {
  draft_pending: "Setup",
  draft_in_progress: "Draft",
  in_progress: "Playing",
  paused: "Paused",
  completed: "Done",
};

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
  managed: "⏱️",
  immersive: "🐌",
};

// ─── Confirm delete dialog ────────────────────────────────────────────────────

function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  deleting,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description: string;
  onConfirm: () => void;
  deleting: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={deleting}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={deleting}>
            {deleting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Script helpers ────────────────────────────────────────────────────────────

type ScriptOption = components["schemas"]["ScriptResponse"];

function scriptLabel(s: ScriptOption) {
  return `${s.sport.toUpperCase()} ${s.season} — ${s.season_type} (${s.total_events} events)`;
}

// ─── Create session dialog ────────────────────────────────────────────────────

// Duration presets: label → wall-clock hours for the full season
const DURATION_PRESETS = [
  { label: "15 min", hours: 0.25 },
  { label: "30 min", hours: 0.5 },
  { label: "1 hour", hours: 1 },
  { label: "2 hours", hours: 2 },
  { label: "4 hours", hours: 4 },
] as const;

const DEFAULT_DURATION_HOURS = 1;

function compressionFactor(totalSimHours: number, wallHours: number): number {
  return Math.ceil(totalSimHours / wallHours);
}

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
  const [durationHours, setDurationHours] = useState(DEFAULT_DURATION_HOURS);
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
  const isImmersive = scriptSpeed === "immersive";

  // Derived: compression_factor to send to the API
  const derivedCompressionFactor =
    isImmersive || !selectedScript
      ? null
      : compressionFactor(selectedScript.total_sim_hours, durationHours);

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
          compression_factor: derivedCompressionFactor,
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

          {/* Speed + Duration — side by side */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Mode</Label>
              <Select value={scriptSpeed} onValueChange={setScriptSpeed}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="blitz">⚡ Blitz</SelectItem>
                  <SelectItem value="managed">⏱️ Managed</SelectItem>
                  <SelectItem value="immersive">🐌 Immersive</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>
                Season duration
                {isImmersive && (
                  <span className="ml-1.5 text-[10px] text-muted-foreground">(real time)</span>
                )}
              </Label>
              <Select
                value={String(durationHours)}
                onValueChange={(v) => setDurationHours(Number(v))}
                disabled={isImmersive}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DURATION_PRESETS.map((p) => (
                    <SelectItem key={p.hours} value={String(p.hours)}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Compression factor hint */}
          {derivedCompressionFactor != null && (
            <p className="text-[11px] text-muted-foreground">
              Compression:{" "}
              <span className="font-mono">{derivedCompressionFactor.toLocaleString()}×</span>
              {" — "}each simulated week plays in ~
              <span className="font-mono">{((durationHours * 60) / 17).toFixed(1)} min</span>
            </p>
          )}

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
  onLeagueDeleted,
}: {
  league: League;
  onLeagueUpdated: (updated: Partial<League>) => void;
  onLeagueDeleted: () => void;
}) {
  const [hasKeys, setHasKeys] = useState<Record<string, boolean>>(league.has_league_keys ?? {});
  const [allowSharedKey, setAllowSharedKey] = useState(league.allow_shared_key);
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  async function handleDeleteLeague() {
    setDeleting(true);
    try {
      await api.DELETE("/leagues/{league_id}", {
        params: { path: { league_id: league.id } },
      });
      onLeagueDeleted();
    } finally {
      setDeleting(false);
    }
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

      {/* Danger zone */}
      <div className="space-y-3 rounded-sm border border-destructive/30 p-4">
        <div>
          <p className="text-sm font-medium text-destructive">Danger zone</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Permanently delete this league, all its sessions, and all member data.
          </p>
        </div>
        <Button
          variant="destructive"
          size="sm"
          className="rounded-sm font-display text-xs uppercase tracking-wide"
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="mr-1.5 h-3.5 w-3.5" />
          Delete league
        </Button>
      </div>

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete league"
        description={`Delete "${league.name}"? All sessions, members, and data will be permanently removed.`}
        onConfirm={handleDeleteLeague}
        deleting={deleting}
      />
    </div>
  );
}

// ─── Sessions panel ───────────────────────────────────────────────────────────

function SessionsPanel({
  league,
  sessions,
  onNewSession,
  canCreate,
  isManager,
  onSessionDeleted,
  onSessionUpdated,
}: {
  league: League;
  sessions: Session[];
  onNewSession: () => void;
  canCreate: boolean;
  isManager: boolean;
  onSessionDeleted: (id: string) => void;
  onSessionUpdated: (id: string, patch: Partial<Session>) => void;
}) {
  const { user } = useAuthStore();
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Track which session is currently mid-start/pause to show a spinner
  const [pendingId, setPendingId] = useState<string | null>(null);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.DELETE("/sessions/{session_id}", {
        params: { path: { session_id: deleteTarget.id } },
      });
      onSessionDeleted(deleteTarget.id);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  async function handleStart(sessionId: string) {
    setPendingId(sessionId);
    try {
      const { data } = await api.POST("/sessions/{session_id}/start", {
        params: { path: { session_id: sessionId } },
      });
      if (data) onSessionUpdated(sessionId, { status: data.status });
    } finally {
      setPendingId(null);
    }
  }

  async function handlePause(sessionId: string) {
    setPendingId(sessionId);
    try {
      const { data } = await api.POST("/sessions/{session_id}/pause", {
        params: { path: { session_id: sessionId } },
      });
      if (data) onSessionUpdated(sessionId, { status: data.status });
    } finally {
      setPendingId(null);
    }
  }

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
          {sessions.map((s) => {
            const isOwner = s.owner_id === user?.id;
            const canPlay = isOwner && (s.status === "draft_pending" || s.status === "paused");
            const canPause = isOwner && s.status === "in_progress";
            const isPending = pendingId === s.id;

            return (
              <div
                key={s.id}
                className="group flex items-center rounded-sm border border-border bg-card transition-all hover:border-primary/30 hover:bg-accent"
              >
                {/* Left — name + metadata; the navigable region */}
                <Link
                  to={`/leagues/${league.id}/sessions/${s.id}`}
                  className="min-w-0 flex-1 px-4 py-3"
                >
                  <div className="flex items-center gap-2">
                    <StatusDot status={s.status} />
                    <p className="truncate font-medium">{s.name}</p>
                  </div>
                  <p className="mt-0.5 pl-4 font-mono text-[10px] text-muted-foreground">
                    {SPEED_EMOJI[s.script_speed] ?? ""} {s.script_speed.toUpperCase()} ·{" "}
                    {s.sport.toUpperCase()} {s.season} · {s.current_teams}/{s.max_teams} teams
                    {s.current_week > 0 && ` · Wk ${s.current_week}`}
                  </p>
                </Link>

                {/* Right — controls; not inside Link to avoid nested interactives */}
                <div className="flex shrink-0 items-center gap-2 pr-3">
                  {/* Status chip */}
                  <SessionStatusBadge status={s.status} />

                  {/* Play / Pause — right of chip */}
                  {(canPlay || canPause) && (
                    <button
                      onClick={() => (canPause ? handlePause(s.id) : handleStart(s.id))}
                      disabled={isPending}
                      title={canPause ? "Pause session" : "Start session"}
                      className={cn(
                        "flex h-6 w-6 items-center justify-center rounded-sm border transition-all",
                        canPause
                          ? "border-primary/30 bg-primary/10 text-primary hover:bg-primary/20"
                          : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground"
                      )}
                    >
                      {isPending ? (
                        <Loader2 className="h-2.5 w-2.5 animate-spin" />
                      ) : canPause ? (
                        <Pause className="h-2.5 w-2.5" />
                      ) : (
                        <Play className="h-2.5 w-2.5 translate-x-px" />
                      )}
                    </button>
                  )}

                  {/* Kebab — manager actions */}
                  {isManager && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 rounded-sm opacity-0 transition-opacity group-hover:opacity-100"
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-40">
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setDeleteTarget(s)}
                        >
                          <Trash2 className="mr-2 h-3.5 w-3.5" />
                          Delete session
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
        title="Delete session"
        description={`Delete "${deleteTarget?.name}"? This is permanent and cannot be undone.`}
        onConfirm={handleDelete}
        deleting={deleting}
      />
    </div>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export function LeaguePage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [league, setLeague] = useState<League | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<ActiveView>(
    (location.state as { activeView?: ActiveView } | null)?.activeView ?? "sessions"
  );
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
      <LeagueSidebar
        league={league}
        sessions={sessions}
        activeView={activeView}
        onNavigateSessions={() => setActiveView("sessions")}
        onNavigateMembers={() => setActiveView("members")}
        onNavigateSettings={isManager ? () => setActiveView("settings") : undefined}
        canCreate={canCreate}
        onCreateSession={() => setCreateOpen(true)}
        onBack={() => navigate("/dashboard")}
        memberCount={members.length}
        footer={
          isMember && !isManager ? (
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
          ) : undefined
        }
      />

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="flex-1 overflow-y-auto px-8 py-8">
          {activeView === "sessions" && (
            <SessionsPanel
              league={league}
              sessions={sessions}
              onNewSession={() => setCreateOpen(true)}
              canCreate={canCreate}
              isManager={isManager}
              onSessionDeleted={(id) => setSessions((prev) => prev.filter((s) => s.id !== id))}
              onSessionUpdated={(id, patch) =>
                setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)))
              }
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
              onLeagueDeleted={() => navigate("/dashboard")}
            />
          )}
        </div>
        {/* end inner scroll area */}
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
