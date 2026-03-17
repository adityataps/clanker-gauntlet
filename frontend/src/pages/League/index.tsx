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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
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
import { api } from "@/api/client";
import { useAuthStore } from "@/store/authStore";
import type { components } from "@/api/schema";

type League = components["schemas"]["LeagueResponse"];
type Member = components["schemas"]["MemberResponse"];
type Session = components["schemas"]["SessionResponse"];
type Invite = components["schemas"]["InviteResponse"];

// ─── Session status badge ─────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  draft_pending: "border-border text-muted-foreground",
  draft_in_progress: "border-sky-500/30 text-sky-400",
  in_progress: "border-primary/30 text-primary",
  paused: "border-amber-500/30 text-amber-400",
  completed: "border-border text-muted-foreground",
};

function SessionStatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();
  const label = key.replace(/_/g, " ");
  return (
    <span
      className={`rounded-sm border px-1.5 py-0.5 font-display text-[9px] font-semibold uppercase tracking-wider ${STATUS_COLORS[key] ?? "border-border text-muted-foreground"}`}
    >
      {label}
    </span>
  );
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
  const [mode, setMode] = useState("blitz");
  const [maxTeams, setMaxTeams] = useState("10");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const { data, error: apiError } = await api.POST("/leagues/{league_id}/sessions", {
        params: { path: { league_id: leagueId } },
        body: {
          name: name.trim(),
          script_id: "00000000-0000-0000-0000-000000000000", // placeholder until script picker lands
          mode,
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
            <Label>Script speed</Label>
            <Select value={mode} onValueChange={setMode}>
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
            <Button type="submit" disabled={!name.trim() || saving}>
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

  async function generateInvite() {
    setLoading(true);
    const { data } = await api.POST("/leagues/{league_id}/invites", {
      params: { path: { league_id: league.id } },
    });
    setLoading(false);
    if (data) setInvite(data);
  }

  const inviteUrl = invite ? `${window.location.origin}/join/${invite.token}` : null;

  async function handleCopy() {
    if (!inviteUrl) return;
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) setInvite(null);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Invite to {league.name}</DialogTitle>
          <DialogDescription>
            Generate a one-time invite link to share with a new member.
          </DialogDescription>
        </DialogHeader>

        {!invite ? (
          <div className="flex justify-center py-4">
            <Button onClick={generateInvite} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Generate invite link
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Input value={inviteUrl ?? ""} readOnly className="font-mono text-xs" />
              <Button size="icon" variant="outline" onClick={handleCopy}>
                {copied ? (
                  <Check className="h-4 w-4 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Expires {new Date(invite.expires_at).toLocaleString()}. Single use.
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Members tab ──────────────────────────────────────────────────────────────

function MembersTab({
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

  async function handleRemove(userId: string) {
    await api.DELETE("/leagues/{league_id}/members/{user_id}", {
      params: { path: { league_id: league.id, user_id: userId } },
    });
    onRefresh();
  }

  async function handlePromote(userId: string) {
    await api.PATCH("/leagues/{league_id}/members/{user_id}", {
      params: { path: { league_id: league.id, user_id: userId } },
      body: { role: "manager" },
    });
    onRefresh();
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {members.length} {members.length === 1 ? "member" : "members"}
        </p>
        {isManager && (
          <Button size="sm" variant="outline" onClick={() => setInviteOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Invite
          </Button>
        )}
      </div>

      <div className="space-y-2">
        {members.map((m) => (
          <div
            key={m.user_id}
            className="flex items-center justify-between rounded-lg border border-border px-4 py-3"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary text-xs font-semibold uppercase">
                {m.display_name.slice(0, 2)}
              </div>
              <div>
                <p className="text-sm font-medium">
                  {m.display_name}
                  {m.user_id === user?.id && (
                    <span className="ml-1.5 text-xs text-muted-foreground">(you)</span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">{m.email}</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Badge
                variant={m.role === "manager" ? "default" : "secondary"}
                className="capitalize"
              >
                {m.role === "manager" && <Crown className="mr-1 h-3 w-3" />}
                {m.role}
              </Badge>

              {isManager && m.user_id !== user?.id && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-7 w-7">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {m.role !== "manager" && (
                      <DropdownMenuItem onClick={() => handlePromote(m.user_id)}>
                        <Crown className="mr-2 h-4 w-4" />
                        Make manager
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onClick={() => handleRemove(m.user_id)}
                    >
                      <UserMinus className="mr-2 h-4 w-4" />
                      Remove from league
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
        ))}
      </div>

      <InviteDialog league={league} open={inviteOpen} onOpenChange={setInviteOpen} />
    </>
  );
}

// ─── Sessions tab ─────────────────────────────────────────────────────────────

function SessionsTab({
  league,
  sessions,
  isManager,
  canCreate,
  onCreated,
}: {
  league: League;
  sessions: Session[];
  isManager: boolean;
  canCreate: boolean;
  onCreated: (s: Session) => void;
}) {
  const [createOpen, setCreateOpen] = useState(false);

  const showCreate = isManager || (canCreate && league.session_creation === "any_member");

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {sessions.length} {sessions.length === 1 ? "session" : "sessions"}
        </p>
        {showCreate && (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            New session
          </Button>
        )}
      </div>

      {sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
          <Layers className="mb-3 h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">No sessions yet.</p>
          {showCreate && (
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => setCreateOpen(true)}
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
              className="flex items-center justify-between rounded-lg border border-border px-4 py-3 transition-colors hover:border-primary/50 hover:bg-accent"
            >
              <div>
                <p className="font-medium">{s.name}</p>
                <p className="text-xs text-muted-foreground capitalize">
                  {s.mode} · {s.sport} · {s.max_teams} teams
                </p>
              </div>
              <SessionStatusBadge status={s.status} />
            </Link>
          ))}
        </div>
      )}

      <CreateSessionDialog
        leagueId={league.id}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={onCreated}
      />
    </>
  );
}

// ─── Settings tab ────────────────────────────────────────────────────────────

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

function SettingsTab({
  league,
  isManager,
  onLeagueUpdated,
}: {
  league: League;
  isManager: boolean;
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

  if (!isManager) {
    return (
      <p className="text-sm text-muted-foreground">Only the league manager can view settings.</p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Shared key toggle */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium">League shared API key</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            When enabled, members without their own LLM key will fall back to the league-level key
            below. Members with their own key always use theirs first.
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
        <>
          <Separator />
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium">Provider keys</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Keys are encrypted at rest. Only set keys for providers your agent teams use. All
                members' agent decisions share these rate limits.
              </p>
            </div>
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
        </>
      )}
    </div>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export function LeaguePage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();
  useAuthStore();

  const [league, setLeague] = useState<League | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    if (!leagueId) return;
    const [leagueRes, membersRes] = await Promise.all([
      api.GET("/leagues/{league_id}", { params: { path: { league_id: leagueId } } }),
      api.GET("/leagues/{league_id}/members", { params: { path: { league_id: leagueId } } }),
    ]);
    setLeague(leagueRes.data ?? null);
    setMembers(membersRes.data ?? []);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, [leagueId]);

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

  return (
    <div className="mx-auto max-w-screen-lg px-4 py-8">
      {/* Header */}
      <Button
        variant="ghost"
        size="sm"
        className="mb-6 -ml-1 text-muted-foreground"
        onClick={() => navigate("/dashboard")}
      >
        <ArrowLeft className="mr-1.5 h-4 w-4" />
        Dashboard
      </Button>

      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl font-bold uppercase tracking-wide">
              {league.name}
            </h1>
            {league.my_role && (
              <Badge variant="secondary" className="capitalize">
                {league.my_role === "manager" && <Crown className="mr-1 h-3 w-3" />}
                {league.my_role}
              </Badge>
            )}
          </div>
          {league.description && (
            <p className="mt-1 text-sm text-muted-foreground">{league.description}</p>
          )}
          <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Users className="h-3.5 w-3.5" />
              {league.member_count} {league.member_count === 1 ? "member" : "members"}
            </span>
            <span className="flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              {league.session_count} {league.session_count === 1 ? "session" : "sessions"}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="sessions">
        <TabsList className="mb-6">
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
          {isManager && <TabsTrigger value="settings">Settings</TabsTrigger>}
        </TabsList>

        <TabsContent value="sessions">
          <Card>
            <CardContent className="pt-6">
              <SessionsTab
                league={league}
                sessions={sessions}
                isManager={isManager}
                canCreate={isMember}
                onCreated={(s) => {
                  setSessions((prev) => [s, ...prev]);
                  setLeague((prev) =>
                    prev ? { ...prev, session_count: prev.session_count + 1 } : prev
                  );
                }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="members">
          <Card>
            <CardContent className="pt-6">
              <MembersTab
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
            </CardContent>
          </Card>
        </TabsContent>

        {isManager && (
          <TabsContent value="settings">
            <Card>
              <CardContent className="pt-6">
                <SettingsTab
                  league={league}
                  isManager={isManager}
                  onLeagueUpdated={(updated) =>
                    setLeague((prev) => (prev ? { ...prev, ...updated } : prev))
                  }
                />
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {/* Leave league (non-managers) */}
      {isMember && !isManager && (
        <div className="mt-8 flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={async () => {
              if (!leagueId) return;
              await api.POST("/leagues/{league_id}/members/me/leave", {
                params: { path: { league_id: leagueId } },
              });
              navigate("/dashboard");
            }}
          >
            Leave league
          </Button>
        </div>
      )}
    </div>
  );
}
