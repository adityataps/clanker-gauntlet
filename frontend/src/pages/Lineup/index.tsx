import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Lock, Save, CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/api/client";

// ── Types ──────────────────────────────────────────────────────────────────

interface RosterPlayer {
  player_id: string;
  name: string;
  position: string;
  nfl_team: string;
  projected_points: number | null;
  status: "ACTIVE" | "QUESTIONABLE" | "DOUBTFUL" | "OUT" | "IR";
  opponent: string | null;
}

type SlotKey = "QB" | "RB1" | "RB2" | "WR1" | "WR2" | "TE" | "FLEX" | "K" | "DEF";

interface LineupState {
  week: number;
  deadline: string | null;
  locked: boolean;
  slots: Record<SlotKey, RosterPlayer | null>;
  bench: RosterPlayer[];
}

type Selection = { type: "slot"; slotKey: SlotKey } | { type: "bench"; playerId: string } | null;
type SaveState = "saved" | "saving" | "unsaved";

// ── Slot config ────────────────────────────────────────────────────────────

const SLOT_DEFS: { key: SlotKey; label: string; eligible: string[] }[] = [
  { key: "QB", label: "QB", eligible: ["QB"] },
  { key: "RB1", label: "RB", eligible: ["RB"] },
  { key: "RB2", label: "RB", eligible: ["RB"] },
  { key: "WR1", label: "WR", eligible: ["WR"] },
  { key: "WR2", label: "WR", eligible: ["WR"] },
  { key: "TE", label: "TE", eligible: ["TE"] },
  { key: "FLEX", label: "FLEX", eligible: ["RB", "WR", "TE"] },
  { key: "K", label: "K", eligible: ["K"] },
  { key: "DEF", label: "DEF", eligible: ["DEF"] },
];

const SLOT_DEF_MAP = Object.fromEntries(SLOT_DEFS.map((s) => [s.key, s]));

// ── Style maps ─────────────────────────────────────────────────────────────

const STATUS_DOT: Record<string, string> = {
  ACTIVE: "bg-emerald-500",
  QUESTIONABLE: "bg-yellow-400",
  DOUBTFUL: "bg-orange-500",
  OUT: "bg-red-500",
  IR: "bg-red-700",
};

const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Active",
  QUESTIONABLE: "Questionable",
  DOUBTFUL: "Doubtful",
  OUT: "Out",
  IR: "IR",
};

// Position accent colors as inline style (avoids Tailwind purge issues with dynamic class names)
const POSITION_HEX: Record<string, string> = {
  QB: "#7c3aed",
  RB: "#059669",
  WR: "#0284c7",
  TE: "#d97706",
  K: "#475569",
  DEF: "#374151",
};

const POSITION_LABEL: Record<string, string> = {
  QB: "QB",
  RB: "RB",
  WR: "WR",
  TE: "TE",
  K: "K",
  DEF: "DEF",
};

// ── API response types ──────────────────────────────────────────────────────

interface LineupApiPlayer {
  player_id: string;
  name: string;
  position: string;
  nfl_team: string | null;
  projected_points: number | null;
  status: string;
  is_starter: boolean;
}

interface LineupApiResponse {
  week: number;
  deadline: string | null;
  locked: boolean;
  roster: LineupApiPlayer[];
}

// ── Slot assignment: map flat roster → LineupState ──────────────────────────

function buildLineupState(data: LineupApiResponse): LineupState {
  const starters = data.roster.filter((p) => p.is_starter);
  const bench: RosterPlayer[] = data.roster
    .filter((p) => !p.is_starter)
    .map((p) => ({ ...p, nfl_team: p.nfl_team ?? "?", opponent: null }));

  const toRosterPlayer = (p: LineupApiPlayer): RosterPlayer => ({
    ...p,
    nfl_team: p.nfl_team ?? "?",
    status: p.status as RosterPlayer["status"],
    opponent: null,
  });

  const slots: LineupState["slots"] = {
    QB: null,
    RB1: null,
    RB2: null,
    WR1: null,
    WR2: null,
    TE: null,
    FLEX: null,
    K: null,
    DEF: null,
  };
  const overflow: RosterPlayer[] = [];

  for (const p of starters) {
    if (p.position === "QB" && !slots.QB) slots.QB = toRosterPlayer(p);
    else if (p.position === "RB" && !slots.RB1) slots.RB1 = toRosterPlayer(p);
    else if (p.position === "RB" && !slots.RB2) slots.RB2 = toRosterPlayer(p);
    else if (p.position === "WR" && !slots.WR1) slots.WR1 = toRosterPlayer(p);
    else if (p.position === "WR" && !slots.WR2) slots.WR2 = toRosterPlayer(p);
    else if (p.position === "TE" && !slots.TE) slots.TE = toRosterPlayer(p);
    else if (p.position === "K" && !slots.K) slots.K = toRosterPlayer(p);
    else if (p.position === "DEF" && !slots.DEF) slots.DEF = toRosterPlayer(p);
    else if (["RB", "WR", "TE"].includes(p.position) && !slots.FLEX) slots.FLEX = toRosterPlayer(p);
    else overflow.push(toRosterPlayer(p));
  }

  return {
    week: data.week,
    deadline: data.deadline,
    locked: data.locked,
    slots,
    bench: [...bench, ...overflow],
  };
}

const EMPTY_LINEUP: LineupState = {
  week: 1,
  deadline: null,
  locked: false,
  slots: {
    QB: null,
    RB1: null,
    RB2: null,
    WR1: null,
    WR2: null,
    TE: null,
    FLEX: null,
    K: null,
    DEF: null,
  },
  bench: [],
};

// ── useCountdown ───────────────────────────────────────────────────────────

function useCountdown(deadline: string | null, locked: boolean): string {
  const [display, setDisplay] = useState("");

  useEffect(() => {
    if (locked) {
      setDisplay("Locked");
      return;
    }
    if (!deadline) {
      setDisplay("");
      return;
    }

    const tick = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) {
        setDisplay("Locked");
        return;
      }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      const s = Math.floor((diff % 60_000) / 1_000);
      setDisplay(h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`);
    };

    tick();
    const id = setInterval(tick, 1_000);
    return () => clearInterval(id);
  }, [deadline, locked]);

  return display;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function projectedTotal(slots: LineupState["slots"]): number {
  return Object.values(slots).reduce((sum, p) => sum + (p?.projected_points ?? 0), 0);
}

// ── PosBadge ───────────────────────────────────────────────────────────────

function PosBadge({ position }: { position: string }) {
  const color = POSITION_HEX[position] ?? "#475569";
  return (
    <span
      className="inline-flex items-center justify-center rounded-sm px-1.5 py-0.5 font-display text-[9px] font-bold uppercase leading-none tracking-wider text-white"
      style={{ backgroundColor: color }}
    >
      {POSITION_LABEL[position] ?? position}
    </span>
  );
}

// ── StatusDot ──────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        STATUS_DOT[status] ?? "bg-muted"
      )}
      title={STATUS_LABEL[status] ?? status}
    />
  );
}

// ── StarterSlotCard ────────────────────────────────────────────────────────

function StarterSlotCard({
  slotDef,
  player,
  selected,
  highlighted,
  locked,
  onClick,
}: {
  slotDef: (typeof SLOT_DEFS)[number];
  player: RosterPlayer | null;
  selected: boolean;
  highlighted: boolean;
  locked: boolean;
  onClick: () => void;
}) {
  const posColor = player ? (POSITION_HEX[player.position] ?? "#475569") : null;
  const isRisky =
    player && (player.status === "DOUBTFUL" || player.status === "OUT" || player.status === "IR");

  return (
    <button
      className={cn(
        "relative w-full overflow-hidden rounded-sm border bg-card p-3 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        locked ? "cursor-default opacity-60" : "cursor-pointer hover:bg-accent",
        selected && "border-primary bg-primary/5",
        highlighted && !selected && "border-primary/40 bg-primary/[0.04]",
        !selected && !highlighted && isRisky && "border-destructive/25",
        !selected && !highlighted && !isRisky && "border-border"
      )}
      onClick={locked ? undefined : onClick}
      disabled={locked}
    >
      {/* Position color strip */}
      {posColor && (
        <span className="absolute inset-y-0 left-0 w-[3px]" style={{ backgroundColor: posColor }} />
      )}

      <div className={cn("flex flex-col gap-2", posColor && "pl-3")}>
        {/* Slot label + status */}
        <div className="flex items-center justify-between">
          <span className="font-display text-[9px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            {slotDef.label}
          </span>
          {player && <StatusDot status={player.status} />}
        </div>

        {player ? (
          <>
            <div className="flex items-center gap-1.5">
              <PosBadge position={player.position} />
              <span className="line-clamp-1 text-sm font-semibold leading-tight">
                {player.name}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] text-muted-foreground">
                {player.nfl_team} · {player.opponent ?? "BYE"}
              </span>
              <span
                className={cn(
                  "font-mono text-sm font-semibold tabular-nums",
                  isRisky ? "text-destructive" : "text-foreground"
                )}
              >
                {player.projected_points?.toFixed(1) ?? "—"}
              </span>
            </div>
          </>
        ) : (
          <span className="font-display text-[10px] uppercase tracking-wider text-muted-foreground/50">
            Empty
          </span>
        )}
      </div>
    </button>
  );
}

// ── BenchRow ───────────────────────────────────────────────────────────────

function BenchRow({
  player,
  selected,
  highlighted,
  dimmed,
  locked,
  onClick,
}: {
  player: RosterPlayer;
  selected: boolean;
  highlighted: boolean;
  dimmed: boolean;
  locked: boolean;
  onClick: () => void;
}) {
  const posColor = POSITION_HEX[player.position] ?? "#475569";

  return (
    <button
      className={cn(
        "flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        locked ? "cursor-default" : "cursor-pointer hover:bg-accent",
        selected && "bg-primary/10 ring-1 ring-inset ring-primary",
        highlighted && !selected && "bg-primary/[0.04]",
        dimmed && "opacity-30"
      )}
      onClick={locked ? undefined : onClick}
      disabled={locked}
    >
      {/* Position strip */}
      <span className="h-4 w-0.5 shrink-0 rounded-full" style={{ backgroundColor: posColor }} />
      <PosBadge position={player.position} />
      <span className="flex-1 truncate text-sm font-medium">{player.name}</span>
      <span className="hidden font-mono text-[10px] text-muted-foreground sm:block">
        {player.nfl_team}
      </span>
      <span className="hidden w-14 text-right font-mono text-[10px] text-muted-foreground sm:block">
        {player.opponent ?? "BYE"}
      </span>
      <StatusDot status={player.status} />
      <span className="w-10 text-right font-mono text-sm font-semibold tabular-nums">
        {player.projected_points?.toFixed(1) ?? "—"}
      </span>
    </button>
  );
}

// ── LineupPage ─────────────────────────────────────────────────────────────

export function LineupPage() {
  const { leagueId, sessionId } = useParams<{ leagueId: string; sessionId: string }>();
  const navigate = useNavigate();

  const [lineup, setLineup] = useState<LineupState>(EMPTY_LINEUP);
  const [loading, setLoading] = useState(true);
  const [selection, setSelection] = useState<Selection>(null);
  const [saveState, setSaveState] = useState<SaveState>("saved");

  // ── Load lineup from API ──────────────────────────────────────────────────

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (api as any)
      .GET(`/sessions/${sessionId}/lineup`)
      .then(({ data }: { data: LineupApiResponse | undefined }) => {
        if (data) setLineup(buildLineupState(data));
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  const countdown = useCountdown(lineup.deadline, lineup.locked);
  const isLocked = lineup.locked || countdown === "Locked";
  const total = useMemo(() => projectedTotal(lineup.slots), [lineup.slots]);

  const isNearDeadline =
    !isLocked &&
    lineup.deadline &&
    new Date(lineup.deadline).getTime() - Date.now() < 30 * 60 * 1_000;

  // ── Eligibility helpers ──────────────────────────────────────────────────

  const highlightedSlots = useMemo((): Set<SlotKey> => {
    const out = new Set<SlotKey>();
    if (!selection) return out;

    if (selection.type === "slot") {
      const selDef = SLOT_DEF_MAP[selection.slotKey];
      const selPlayer = lineup.slots[selection.slotKey];
      for (const sd of SLOT_DEFS) {
        if (sd.key === selection.slotKey) continue;
        const otherPlayer = lineup.slots[sd.key];
        const otherFitsHere = otherPlayer ? selDef.eligible.includes(otherPlayer.position) : true;
        const selFitsThere = selPlayer ? sd.eligible.includes(selPlayer.position) : true;
        if (otherFitsHere && selFitsThere) out.add(sd.key);
      }
    }

    if (selection.type === "bench") {
      const bp = lineup.bench.find((p) => p.player_id === selection.playerId);
      if (bp) {
        for (const sd of SLOT_DEFS) {
          if (sd.eligible.includes(bp.position)) out.add(sd.key);
        }
      }
    }

    return out;
  }, [selection, lineup]);

  const highlightedBench = useMemo((): Set<string> => {
    if (!selection || selection.type !== "slot") return new Set();
    const slotDef = SLOT_DEF_MAP[selection.slotKey];
    return new Set(
      lineup.bench.filter((p) => slotDef.eligible.includes(p.position)).map((p) => p.player_id)
    );
  }, [selection, lineup]);

  // ── Swap operations ──────────────────────────────────────────────────────

  function swapTwoSlots(a: SlotKey, b: SlotKey) {
    setLineup((prev) => {
      const s = { ...prev.slots };
      [s[a], s[b]] = [s[b], s[a]];
      return { ...prev, slots: s };
    });
    setSaveState("unsaved");
    setSelection(null);
  }

  function swapBenchIntoSlot(slotKey: SlotKey, playerId: string) {
    setLineup((prev) => {
      const benchPlayer = prev.bench.find((p) => p.player_id === playerId)!;
      const displaced = prev.slots[slotKey];
      const newBench = displaced
        ? prev.bench.map((p) => (p.player_id === playerId ? displaced : p))
        : prev.bench.filter((p) => p.player_id !== playerId);
      return { ...prev, slots: { ...prev.slots, [slotKey]: benchPlayer }, bench: newBench };
    });
    setSaveState("unsaved");
    setSelection(null);
  }

  // ── Click handlers ───────────────────────────────────────────────────────

  function handleSlotClick(slotKey: SlotKey) {
    if (isLocked) return;

    if (!selection) {
      setSelection({ type: "slot", slotKey });
      return;
    }

    if (selection.type === "slot") {
      if (selection.slotKey === slotKey) {
        setSelection(null);
        return;
      }
      if (highlightedSlots.has(slotKey)) {
        swapTwoSlots(selection.slotKey, slotKey);
        return;
      }
      setSelection({ type: "slot", slotKey });
      return;
    }

    if (selection.type === "bench") {
      if (highlightedSlots.has(slotKey)) {
        swapBenchIntoSlot(slotKey, selection.playerId);
        return;
      }
      setSelection({ type: "slot", slotKey });
    }
  }

  function handleBenchClick(playerId: string) {
    if (isLocked) return;

    if (!selection) {
      setSelection({ type: "bench", playerId });
      return;
    }

    if (selection.type === "bench") {
      setSelection(selection.playerId === playerId ? null : { type: "bench", playerId });
      return;
    }

    if (selection.type === "slot") {
      if (highlightedBench.has(playerId)) {
        swapBenchIntoSlot(selection.slotKey, playerId);
        return;
      }
      setSelection({ type: "bench", playerId });
    }
  }

  // ── Save ─────────────────────────────────────────────────────────────────

  const saveLineup = useCallback(async () => {
    if (saveState !== "unsaved" || !sessionId) return;
    setSaveState("saving");
    try {
      const starters = Object.values(lineup.slots)
        .filter(Boolean)
        .map((p) => p!.player_id);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (api as any).PUT(`/sessions/${sessionId}/lineup`, {
        body: { starters, week: lineup.week },
      });
      setSaveState("saved");
    } catch {
      setSaveState("unsaved");
    }
  }, [saveState, sessionId, lineup.slots, lineup.week]);

  useEffect(() => {
    if (saveState !== "unsaved") return;
    const id = setTimeout(saveLineup, 1_500);
    return () => clearTimeout(id);
  }, [saveState, saveLineup]);

  // ── Render ───────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center py-24">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-7">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            className="flex items-center gap-1.5 font-display text-xs uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => navigate(`/leagues/${leagueId}/sessions/${sessionId}`)}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Session
          </button>
          <span className="text-border">·</span>
          <h1 className="font-display text-2xl font-bold uppercase tracking-wide text-foreground">
            Week {lineup.week} Lineup
          </h1>
        </div>

        {/* Save indicator */}
        <div className="flex items-center gap-2">
          {saveState === "saved" && (
            <span className="flex items-center gap-1.5 font-display text-[10px] uppercase tracking-wider text-emerald-500">
              <CheckCircle2 className="h-3 w-3" />
              Saved
            </span>
          )}
          {saveState === "saving" && (
            <span className="flex animate-pulse items-center gap-1.5 font-display text-[10px] uppercase tracking-wider text-muted-foreground">
              <Save className="h-3 w-3" />
              Saving…
            </span>
          )}
          {saveState === "unsaved" && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 rounded-sm font-display text-[10px] uppercase tracking-wider"
              onClick={saveLineup}
            >
              Save now
            </Button>
          )}
        </div>
      </div>

      {/* Deadline / lock bar */}
      <div
        className={cn(
          "mb-6 flex items-center justify-between rounded-sm border px-4 py-3",
          isLocked
            ? "border-destructive/20 bg-destructive/[0.06]"
            : isNearDeadline
              ? "border-amber-500/25 bg-amber-500/[0.06]"
              : "border-border bg-card"
        )}
      >
        <div className="flex items-center gap-2.5">
          {isLocked ? (
            <Lock className={cn("h-3.5 w-3.5", isLocked ? "text-destructive" : "")} />
          ) : (
            <span
              className={cn(
                "h-2 w-2 animate-pulse rounded-full",
                isNearDeadline ? "bg-amber-400" : "bg-emerald-500"
              )}
            />
          )}
          <span
            className={cn(
              "font-display text-xs font-semibold uppercase tracking-[0.15em]",
              isLocked ? "text-destructive" : isNearDeadline ? "text-amber-400" : "text-foreground"
            )}
          >
            {isLocked ? "Lineup locked" : "Locks in"}
          </span>
          {!isLocked && (
            <span
              className={cn(
                "font-mono text-sm tabular-nums",
                isNearDeadline ? "text-amber-400" : "text-muted-foreground"
              )}
            >
              {countdown}
            </span>
          )}
        </div>
        <div className="text-right">
          <span className="font-display text-[10px] uppercase tracking-wider text-muted-foreground">
            Projected
          </span>
          <span className="ml-2 font-mono text-base font-semibold tabular-nums text-foreground">
            {total.toFixed(1)}
          </span>
        </div>
      </div>

      {/* Section: Starters */}
      <div className="mb-2 flex items-center gap-3">
        <span className="font-display text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Starters
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <div className="mb-1 grid grid-cols-3 gap-2">
        {SLOT_DEFS.map((sd) => (
          <StarterSlotCard
            key={sd.key}
            slotDef={sd}
            player={lineup.slots[sd.key]}
            selected={selection?.type === "slot" && selection.slotKey === sd.key}
            highlighted={highlightedSlots.has(sd.key)}
            locked={isLocked}
            onClick={() => handleSlotClick(sd.key)}
          />
        ))}
      </div>

      {/* Swap hint */}
      {!isLocked && (
        <p className="mb-5 mt-1 font-display text-[10px] uppercase tracking-wider text-muted-foreground/60">
          {selection ? "Select a highlighted slot to swap." : "Click any player to begin a swap."}
        </p>
      )}

      {/* Section: Bench */}
      <div className="mb-2 mt-5 flex items-center gap-3">
        <span className="font-display text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Bench
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <div className="rounded-sm border border-border bg-card">
        {lineup.bench.length === 0 ? (
          <p className="py-6 text-center font-display text-xs uppercase tracking-wider text-muted-foreground">
            No bench players.
          </p>
        ) : (
          <div className="divide-y divide-border/50">
            {lineup.bench.map((p) => (
              <BenchRow
                key={p.player_id}
                player={p}
                selected={selection?.type === "bench" && selection.playerId === p.player_id}
                highlighted={highlightedBench.has(p.player_id)}
                dimmed={
                  !!selection && selection.type === "slot" && !highlightedBench.has(p.player_id)
                }
                locked={isLocked}
                onClick={() => handleBenchClick(p.player_id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Status legend */}
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {Object.entries(STATUS_LABEL).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[k])} />
            <span className="font-display text-[9px] uppercase tracking-wider text-muted-foreground">
              {v}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
