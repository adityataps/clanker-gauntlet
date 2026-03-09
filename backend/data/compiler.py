"""
ScriptCompiler

Pulls historical NFL data from the Sleeper API and writes a chronologically
ordered event log into season_scripts + season_events DB tables.

The compiled script is a global asset — one record per sport+season+season_type,
shared across all sessions that backtest the same season.

Usage (CLI):
    python -m backend.data.compiler --sport nfl --season 2025

Usage (programmatic):
    async with AsyncSessionLocal() as db:
        compiler = ScriptCompiler(db)
        script = await compiler.compile("nfl", 2025)
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.data.providers.sleeper import get_players, get_stats
from backend.db.models import ScriptStatus, SeasonEvent, SeasonScript, SeasonType
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Week 1 2025 NFL season kickoff — Chiefs vs Ravens Thursday Night Football
# September 5, 2025 ~00:20 UTC (8:20 PM ET Sept 4)
NFL_2025_KICKOFF = datetime(2025, 9, 5, 0, 20, tzinfo=UTC)

NFL_REGULAR_WEEKS = 17

# Only generate SCORE_UPDATE events for fantasy-relevant positions
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}

# Batch size for season_events inserts
BATCH_SIZE = 500

# sim_offset_hours within each week (week base = (week - 1) * 168)
# Offsets chosen to mirror real NFL week structure:
#   Wed/Thu: lineup window opens → Thursday night lock
#   Sun–Mon: games play out
#   Tue:     week fully scored
#   Wed:     waivers resolve, next week begins
_OFF_LINEUP_OPEN = 0.0  # lineup agent window opens
_OFF_ROSTER_LOCK = 60.0  # Thursday night lock
_OFF_LINEUP_CLOSE = 60.1  # lineup window closes
_OFF_GAME_START = 60.2  # games begin
_OFF_SCORE_UPDATE = 108.0  # end-of-week stats batch
_OFF_WEEK_END = 120.0  # final scores locked
_OFF_WAIVER_OPEN = 120.1  # FAAB window opens
_OFF_WAIVER_WINDOW = 144.0  # waiver agent window opens
_OFF_WAIVER_RESOLVED = 167.9  # bids resolved (just before next week)


# ---------------------------------------------------------------------------
# ScriptCompiler
# ---------------------------------------------------------------------------


class ScriptCompiler:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def compile(
        self,
        sport: str,
        season: int,
        season_type: str = "regular",
        force: bool = False,
    ) -> SeasonScript:
        """
        Compile a full season into season_events rows.
        Returns the SeasonScript record (existing or newly compiled).

        force=True will delete and recompile an existing script.
        """
        season_type_enum = SeasonType(season_type)

        # Check for existing compiled script
        existing = await self._find_existing(sport, season, season_type_enum)
        if existing and existing.status == ScriptStatus.COMPILED and not force:
            console.print(
                f"[green]Script already compiled:[/green] {sport} {season} "
                f"{season_type} ({existing.total_events} events)"
            )
            return existing

        if existing and force:
            console.print("[yellow]Force recompile — deleting existing script...[/yellow]")
            await self.db.delete(existing)
            await self.db.commit()

        # Create a new pending script record
        script = SeasonScript(
            sport=sport,
            season=season,
            season_type=season_type_enum,
            status=ScriptStatus.PENDING,
        )
        self.db.add(script)
        await self.db.commit()
        await self.db.refresh(script)

        try:
            total = await self._compile_nfl(script)
            script.status = ScriptStatus.COMPILED
            script.total_events = total
            script.compiled_at = datetime.now(UTC)
            await self.db.commit()
            console.print(
                f"[green]Compiled:[/green] {sport} {season} {season_type} — {total} events written"
            )
            return script

        except Exception as exc:
            script.status = ScriptStatus.FAILED
            await self.db.commit()
            logger.exception("ScriptCompiler failed for %s %s %s", sport, season, season_type)
            raise RuntimeError(f"ScriptCompiler failed: {exc}") from exc

    # -----------------------------------------------------------------------
    # NFL compilation
    # -----------------------------------------------------------------------

    async def _compile_nfl(self, script: SeasonScript) -> int:
        """
        Compile NFL regular season. Returns total event count.
        Inserts season_events rows in batches of BATCH_SIZE.
        """
        console.print(f"Fetching player universe for NFL {script.season}...")
        players = await get_players()
        player_positions = {pid: p.position for pid, p in players.items() if p.position}

        events_buffer: list[SeasonEvent] = []
        seq = 1

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} weeks"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Compiling weeks...", total=NFL_REGULAR_WEEKS)

            for week in range(1, NFL_REGULAR_WEEKS + 1):
                week_base = (week - 1) * 168.0
                progress.update(task, description=f"Week {week:2d} — fetching stats...")

                # Fetch actual stats for this week
                stats = await get_stats(season=script.season, week=week, season_type="regular")

                progress.update(task, description=f"Week {week:2d} — generating events...")

                # Generate fixed structural events for this week
                week_events = self._week_structural_events(script, week, week_base, seq)
                seq += len(week_events)

                # Generate SCORE_UPDATE events from actual stats
                score_events, seq = self._score_update_events(
                    script, week, week_base, stats, player_positions, seq
                )

                # Merge and sort all events for this week by offset
                all_week = sorted(week_events + score_events, key=lambda e: e.sim_offset_hours)
                events_buffer.extend(all_week)

                # Flush buffer in batches to avoid session bloat
                while len(events_buffer) >= BATCH_SIZE:
                    batch = events_buffer[:BATCH_SIZE]
                    events_buffer = events_buffer[BATCH_SIZE:]
                    self.db.add_all(batch)
                    await self.db.commit()

                progress.advance(task)

        # SEASON_END event
        season_end_offset = (NFL_REGULAR_WEEKS - 1) * 168.0 + _OFF_WEEK_END + 1.0
        events_buffer.append(
            SeasonEvent(
                script_id=script.id,
                seq=seq,
                event_type="SEASON_END",
                payload={"season": script.season, "season_type": "regular"},
                week_number=NFL_REGULAR_WEEKS,
                sim_offset_hours=season_end_offset,
            )
        )
        seq += 1

        # Flush remaining events
        if events_buffer:
            self.db.add_all(events_buffer)
            await self.db.commit()

        return seq - 1  # total events written

    def _week_structural_events(
        self,
        script: SeasonScript,
        week: int,
        week_base: float,
        seq_start: int,
    ) -> list[SeasonEvent]:
        """Generate the fixed structural events for a week (no stats)."""
        seq = seq_start
        events = []

        def ev(event_type: str, offset: float, payload: dict) -> SeasonEvent:
            nonlocal seq
            e = SeasonEvent(
                script_id=script.id,
                seq=seq,
                event_type=event_type,
                payload=payload,
                week_number=week,
                sim_offset_hours=week_base + offset,
            )
            seq += 1
            return e

        events.append(
            ev(
                "AGENT_WINDOW_OPEN",
                _OFF_LINEUP_OPEN,
                {"type": "lineup", "week": week, "deadline_offset_hours": _OFF_ROSTER_LOCK},
            )
        )
        events.append(ev("ROSTER_LOCK", _OFF_ROSTER_LOCK, {"week": week}))
        events.append(ev("AGENT_WINDOW_CLOSE", _OFF_LINEUP_CLOSE, {"type": "lineup", "week": week}))
        events.append(ev("GAME_START", _OFF_GAME_START, {"week": week}))
        events.append(ev("WEEK_END", _OFF_WEEK_END, {"week": week}))
        events.append(ev("WAIVER_OPEN", _OFF_WAIVER_OPEN, {"week": week}))
        events.append(
            ev(
                "AGENT_WINDOW_OPEN",
                _OFF_WAIVER_WINDOW,
                {"type": "waiver", "week": week, "deadline_offset_hours": _OFF_WAIVER_RESOLVED},
            )
        )
        events.append(ev("WAIVER_RESOLVED", _OFF_WAIVER_RESOLVED, {"week": week}))

        return events

    def _score_update_events(
        self,
        script: SeasonScript,
        week: int,
        week_base: float,
        stats: dict,
        player_positions: dict[str, str],
        seq_start: int,
    ) -> tuple[list[SeasonEvent], int]:
        """
        Generate SCORE_UPDATE events for all fantasy-relevant players
        who scored > 0 half-PPR points in the week.
        """
        seq = seq_start
        events = []

        for player_id, stat in stats.items():
            # Filter to fantasy-relevant positions
            pos = player_positions.get(player_id)
            if pos not in FANTASY_POSITIONS:
                continue

            pts = stat.pts_half_ppr
            if pts is None or pts <= 0:
                continue

            # Build a compact stats payload (exclude None values)
            stat_fields = {
                "pass_yd": stat.pass_yd,
                "pass_td": stat.pass_td,
                "pass_int": stat.pass_int,
                "rush_yd": stat.rush_yd,
                "rush_td": stat.rush_td,
                "rec": stat.rec,
                "rec_yd": stat.rec_yd,
                "rec_td": stat.rec_td,
                "fum_lost": stat.fum_lost,
            }
            stats_payload = {k: v for k, v in stat_fields.items() if v is not None and v != 0.0}

            events.append(
                SeasonEvent(
                    script_id=script.id,
                    seq=seq,
                    event_type="SCORE_UPDATE",
                    payload={
                        "player_id": player_id,
                        "week": week,
                        "pts_half_ppr": pts,
                        "stats": stats_payload,
                    },
                    week_number=week,
                    sim_offset_hours=week_base + _OFF_SCORE_UPDATE,
                )
            )
            seq += 1

        return events, seq

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    async def _find_existing(
        self, sport: str, season: int, season_type: SeasonType
    ) -> SeasonScript | None:
        result = await self.db.execute(
            select(SeasonScript).where(
                SeasonScript.sport == sport,
                SeasonScript.season == season,
                SeasonScript.season_type == season_type,
            )
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Compile a season script into the DB")
    parser.add_argument("--sport", default="nfl", choices=["nfl", "nba", "mlb"])
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--season-type", default="regular", choices=["regular", "playoff"])
    parser.add_argument("--force", action="store_true", help="Recompile even if already exists")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    console.print(
        f"[bold]Clanker Gauntlet — ScriptCompiler[/bold]\n"
        f"Sport: [cyan]{args.sport}[/cyan]  "
        f"Season: [cyan]{args.season}[/cyan]  "
        f"Type: [cyan]{args.season_type}[/cyan]"
    )

    async with AsyncSessionLocal() as db:
        compiler = ScriptCompiler(db)
        await compiler.compile(
            sport=args.sport,
            season=args.season,
            season_type=args.season_type,
            force=args.force,
        )


if __name__ == "__main__":
    asyncio.run(_main())
