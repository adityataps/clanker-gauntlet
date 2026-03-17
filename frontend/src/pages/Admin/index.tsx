import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Database,
  Layers,
  RefreshCw,
  Terminal,
  Users,
  Zap,
} from "lucide-react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";

type AdminStats = components["schemas"]["AdminStats"];
type AdminUser = components["schemas"]["AdminUser"];
type AdminLeague = components["schemas"]["AdminLeague"];
type AdminScript = components["schemas"]["AdminScript"];
type CompileResponse = components["schemas"]["CompileResponse"];

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(date: string | null): string {
  if (!date) return "—";
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function fmtTime(date: string): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="mb-4 flex items-center gap-3 border-l-2 border-primary pl-3">
      <Icon className="h-4 w-4 text-primary" />
      <span className="font-display text-xs font-bold uppercase tracking-[0.2em] text-foreground">
        {label}
      </span>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  delay,
}: {
  label: string;
  value: number | null;
  icon: React.ElementType;
  delay: number;
}) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div
      className="border border-border bg-card p-5 transition-opacity duration-500"
      style={{ opacity: visible ? 1 : 0 }}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="font-display text-[10px] font-bold uppercase tracking-[0.25em] text-muted-foreground">
          {label}
        </span>
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <span className="font-display text-4xl font-bold tabular-nums text-foreground">
        {value === null ? (
          <span className="h-8 w-16 animate-pulse rounded-sm bg-muted inline-block" />
        ) : (
          value.toLocaleString()
        )}
      </span>
    </div>
  );
}

function ScriptStatusBadge({ status }: { status: string }) {
  if (status === "compiled") {
    return (
      <span className="inline-flex items-center gap-1 rounded-sm border border-primary/30 bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-primary">
        <CheckCircle className="h-2.5 w-2.5" />
        compiled
      </span>
    );
  }
  if (status === "pending") {
    return (
      <span className="inline-flex animate-pulse items-center gap-1 rounded-sm border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-amber-400">
        <Clock className="h-2.5 w-2.5" />
        pending
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-destructive/30 bg-destructive/10 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-destructive">
      <AlertTriangle className="h-2.5 w-2.5" />
      failed
    </span>
  );
}

// ── Compiler form ─────────────────────────────────────────────────────────────

function CompilerSection({
  scripts,
  onScriptsRefresh,
}: {
  scripts: AdminScript[];
  onScriptsRefresh: () => void;
}) {
  const [sport, setSport] = useState("nfl");
  const [season, setSeason] = useState("2025");
  const [seasonType, setSeasonType] = useState("regular");
  const [force, setForce] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [result, setResult] = useState<CompileResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => {
    return () => stopPolling();
  }, []);

  // Poll until result status is no longer "pending"
  useEffect(() => {
    if (!result || result.status !== "pending") {
      stopPolling();
      return;
    }
    stopPolling();
    pollRef.current = setInterval(async () => {
      const { data } = await api.GET("/admin/scripts");
      if (!data) return;
      const matching = data.find((s) => s.id === result.script_id);
      if (matching && matching.status !== "pending") {
        setResult((prev) => prev && { ...prev, status: matching.status });
        onScriptsRefresh();
        stopPolling();
      }
    }, 3000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.script_id, result?.status]);

  async function handleCompile() {
    setCompiling(true);
    setResult(null);
    try {
      const { data, error } = await api.POST("/admin/scripts/compile", {
        body: {
          sport,
          season: parseInt(season, 10),
          season_type: seasonType,
          force,
        },
      });
      if (error) {
        setResult({
          script_id: "",
          status: "failed",
          message: String((error as { detail?: string }).detail ?? "Unknown error"),
        });
      } else if (data) {
        setResult(data);
        onScriptsRefresh();
      }
    } finally {
      setCompiling(false);
    }
  }

  const selectCls =
    "h-8 rounded-sm border border-border bg-input px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary";
  const inputCls =
    "h-8 w-24 rounded-sm border border-border bg-input px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary";

  return (
    <div>
      {/* Form */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            sport
          </label>
          <select value={sport} onChange={(e) => setSport(e.target.value)} className={selectCls}>
            <option value="nfl">nfl</option>
            <option value="nba">nba</option>
            <option value="mlb">mlb</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            season
          </label>
          <input
            type="number"
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            className={inputCls}
            min={2020}
            max={2030}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            type
          </label>
          <select
            value={seasonType}
            onChange={(e) => setSeasonType(e.target.value)}
            className={selectCls}
          >
            <option value="regular">regular</option>
            <option value="preseason">preseason</option>
            <option value="playoff">playoff</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="force-compile"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
            className="h-3.5 w-3.5 accent-amber-400"
          />
          <label
            htmlFor="force-compile"
            className="font-mono text-xs text-muted-foreground cursor-pointer select-none"
          >
            force
          </label>
        </div>

        <button
          onClick={handleCompile}
          disabled={compiling}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-amber-500/50 bg-amber-500/10 px-4 font-mono text-xs font-bold uppercase tracking-wider text-amber-400 transition-colors hover:bg-amber-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {compiling ? (
            <>
              <RefreshCw className="h-3 w-3 animate-spin" />
              compiling…
            </>
          ) : (
            <>
              <Terminal className="h-3 w-3" />
              compile
            </>
          )}
        </button>
      </div>

      {/* Result banner */}
      {result && (
        <div
          className={`mb-4 flex items-start gap-2 rounded-sm border px-3 py-2 font-mono text-xs ${
            result.status === "compiled"
              ? "border-primary/30 bg-primary/5 text-primary"
              : result.status === "failed"
                ? "border-destructive/30 bg-destructive/5 text-destructive"
                : "border-amber-500/30 bg-amber-500/5 text-amber-400"
          }`}
        >
          {result.status === "pending" && (
            <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-pulse" />
          )}
          {result.status === "compiled" && <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          {result.status === "failed" && <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span>{result.message}</span>
          {result.status === "pending" && (
            <span className="ml-auto shrink-0 text-muted-foreground">polling every 3s…</span>
          )}
        </div>
      )}

      {/* Scripts table */}
      {scripts.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {["sport", "season", "type", "events", "compiled", "status"].map((h) => (
                  <th
                    key={h}
                    className="pb-2 pr-6 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scripts.map((s) => (
                <tr key={s.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="py-2.5 pr-6 font-mono text-xs uppercase text-foreground">
                    {s.sport}
                  </td>
                  <td className="py-2.5 pr-6 font-mono text-xs tabular-nums text-foreground">
                    {s.season}
                  </td>
                  <td className="py-2.5 pr-6 font-mono text-xs text-muted-foreground">
                    {s.season_type}
                  </td>
                  <td className="py-2.5 pr-6 font-mono text-xs tabular-nums text-foreground">
                    {s.total_events.toLocaleString()}
                  </td>
                  <td className="py-2.5 pr-6 font-mono text-xs tabular-nums text-muted-foreground">
                    {fmt(s.compiled_at)}
                  </td>
                  <td className="py-2.5">
                    <ScriptStatusBadge status={s.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function AdminPage() {
  const [denied, setDenied] = useState(false);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [leagues, setLeagues] = useState<AdminLeague[]>([]);
  const [scripts, setScripts] = useState<AdminScript[]>([]);

  async function loadAll() {
    const [statsRes, usersRes, leaguesRes, scriptsRes] = await Promise.all([
      api.GET("/admin/stats"),
      api.GET("/admin/users"),
      api.GET("/admin/leagues"),
      api.GET("/admin/scripts"),
    ]);

    // Check for 403 on any response
    if (statsRes.response?.status === 403 || statsRes.response?.status === 503) {
      setDenied(true);
      return;
    }

    if (statsRes.data) setStats(statsRes.data);
    if (usersRes.data) setUsers(usersRes.data);
    if (leaguesRes.data) setLeagues(leaguesRes.data);
    if (scriptsRes.data) setScripts(scriptsRes.data);
  }

  async function refreshScripts() {
    const { data } = await api.GET("/admin/scripts");
    if (data) setScripts(data);
  }

  useEffect(() => {
    loadAll();
  }, []);

  if (denied) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-sm border border-destructive/30 bg-destructive/10">
          <AlertTriangle className="h-5 w-5 text-destructive" />
        </div>
        <p className="font-display text-2xl font-bold uppercase tracking-wide text-foreground">
          Access Denied
        </p>
        <p className="mt-2 font-mono text-xs text-muted-foreground">
          This area requires server-admin privileges.
        </p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Set <span className="text-foreground">ADMIN_EMAILS</span> in your environment to grant
          access.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-10">
      {/* Page header */}
      <div className="mb-10 border-b border-border pb-6">
        <p className="mb-1 font-display text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          Server
        </p>
        <h1 className="font-display text-4xl font-bold uppercase tracking-wide text-foreground">
          Admin Control
        </h1>
      </div>

      {/* Stat cards */}
      <div className="mb-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Users" value={stats?.user_count ?? null} icon={Users} delay={0} />
        <StatCard label="Leagues" value={stats?.league_count ?? null} icon={Layers} delay={80} />
        <StatCard label="Sessions" value={stats?.session_count ?? null} icon={Zap} delay={160} />
        <StatCard label="Scripts" value={stats?.script_count ?? null} icon={Database} delay={240} />
      </div>

      {/* Script Compiler */}
      <section className="mb-10 rounded-sm border border-border bg-card p-6">
        <SectionHeader icon={Terminal} label="Script Compiler" />
        <CompilerSection scripts={scripts} onScriptsRefresh={refreshScripts} />
      </section>

      {/* Users */}
      <section className="mb-10 rounded-sm border border-border bg-card p-6">
        <SectionHeader icon={Users} label={`Users · ${users.length}`} />
        {users.length === 0 ? (
          <p className="font-mono text-xs text-muted-foreground">No users found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {["email", "display name", "joined"].map((h) => (
                    <th
                      key={h}
                      className="pb-2 pr-8 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="py-2.5 pr-8 font-mono text-xs text-foreground">{u.email}</td>
                    <td className="py-2.5 pr-8 font-mono text-xs text-muted-foreground">
                      {u.display_name}
                    </td>
                    <td className="py-2.5 font-mono text-xs tabular-nums text-muted-foreground">
                      {fmtTime(u.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Leagues */}
      <section className="rounded-sm border border-border bg-card p-6">
        <SectionHeader icon={Layers} label={`Leagues · ${leagues.length}`} />
        {leagues.length === 0 ? (
          <p className="font-mono text-xs text-muted-foreground">No leagues found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {["name", "members", "sessions", "created"].map((h) => (
                    <th
                      key={h}
                      className="pb-2 pr-8 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leagues.map((l) => (
                  <tr key={l.id} className="border-b border-border/50 hover:bg-accent/30">
                    <td className="py-2.5 pr-8 font-mono text-xs text-foreground">{l.name}</td>
                    <td className="py-2.5 pr-8 font-mono text-xs tabular-nums text-foreground">
                      {l.member_count}
                    </td>
                    <td className="py-2.5 pr-8 font-mono text-xs tabular-nums text-foreground">
                      {l.session_count}
                    </td>
                    <td className="py-2.5 font-mono text-xs tabular-nums text-muted-foreground">
                      {fmtTime(l.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
