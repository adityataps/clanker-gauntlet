# Clanker Gauntlet

A fantasy sports simulation platform where AI agents and human players compete in fantasy leagues. Agents make autonomous roster decisions based on player projections and news feeds. Supports backtesting against historical seasons and real-time play alongside live NFL seasons.

---

## Vision

Multiple AI agents — each with a distinct personality — compete in a fantasy league alongside human players. Agents use the Claude API to reason about lineup decisions, waiver pickups, and trades. The platform runs week-by-week, scoring outcomes against real NFL stats. Human players participate via a web UI with the same information agents receive.

---

## Terminology

| Term             | Definition                                                                                                                                                                                                                                                                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Season**       | A real-world sports season (e.g., the 2025 NFL regular season). Seasons are not stored — they are the source from which Scripts are compiled.                                                                                                                                                                                                                            |
| **Script**       | A compiled, chronological list of events from a season. Stored in the DB (`season_scripts` + `season_events`). Shared across all sessions that backtest the same season. Two types: **post-season** (pre-compiled from a completed season, playable at any speed) and **live-season** (compiled in real-time as the current season unfolds, must run in Immersive mode). |
| **Session**      | A user-created league playback of a script. Multiple users can belong to the same session; each user controls one team. Multiple sessions can run the same script concurrently and independently.                                                                                                                                                                        |
| **Script Speed** | How fast a session plays back the script and how it handles agent decision windows.                                                                                                                                                                                                                                                                                      |
| **Waiver Mode**  | How contested player pickups are resolved each week.                                                                                                                                                                                                                                                                                                                     |

### Script Speeds

| Speed         | Key         | Behavior                                                                                                                                                                                                                                                                                      |
| ------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Blitz**     | `blitz`     | Plays through the script as fast as possible. Agents must act quickly — the runner does not wait for them. Context is pre-loaded via lookahead so agents start with full information. Best for backtesting and agent tuning.                                                                  |
| **Managed**   | `managed`   | Plays at a compressed wall-clock ratio (e.g., a 17-week season in 17 days). The runner pauses at each agent window and waits for all teams to submit decisions before advancing. Agents get a fair chance. Best for leagues with friends who want a real season without a 17-week commitment. |
| **Immersive** | `immersive` | Plays at 1:1 real-world time. Works with both post-season and live-season scripts. The runner does not wait for agents — deadlines are real timestamps. Context arrives via live feed as events happen. Best for the full fantasy season experience.                                          |

### Waiver Modes

| Mode         | How it works                                                                                                                                                                                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **FAAB**     | Sealed-bid auction. Each team gets a seasonal budget ($100 default, never resets). Teams bid secretly; the highest dollar wins each contested player and the bid is permanently deducted. Ties broken by waiver priority. Unlimited claims per waiver period. |
| **Priority** | Ordered claims. Teams are ranked in priority order; the highest-priority team gets each contested player. No budget involved — claims are free. One successful claim per team per waiver period (standard league rules).                                      |

#### Priority Reset Modes (Priority waiver mode only)

| Reset                | Behavior                                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Rolling**          | The team that wins a claim drops to the bottom of the priority list. Non-winners retain their relative order. Most common in Yahoo/ESPN leagues.                                      |
| **Season-long**      | Priority is assigned once at the start of the season (e.g., reverse of draft order) and never changes.                                                                                |
| **Weekly standings** | Priority is re-ranked every week: worst record → highest priority. Tiebreaker: fewer points scored = higher priority. Gives struggling teams the best shot at improving their roster. |

---

## Core Invariant

> **The EventRunner is the single source of truth. Agents observe events and submit intentions. The runner resolves all intentions into state transitions atomically.**

Agents are stateless advisors. They never directly mutate shared state.

---

## Tech Stack

| Layer                             | Choice                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------- |
| Runtime                           | Python 3.13, `uv` for dependency management                                                       |
| Backend                           | FastAPI (async REST + WebSocket)                                                                  |
| DB                                | PostgreSQL (docker-compose locally, managed cloud in production)                                  |
| Migrations                        | Alembic                                                                                           |
| Cache / Scheduler store / Pub-sub | Redis                                                                                             |
| Scheduler                         | APScheduler (Redis job store for MANAGED/IMMERSIVE modes)                                         |
| Auth                              | Auth0 (primary); JWT username/password fallback (server-admin toggle via env var)                 |
| Agent reasoning                   | Anthropic SDK — tool-use loop (Phase 1), multi-agent orchestration (Phase 3)                      |
| Agent concurrency                 | In-process asyncio coroutines (Phase 1–2); Docker / Cloud Run containers (Phase 3+)               |
| Frontend                          | React + Vite                                                                                      |
| Frontend state                    | Zustand                                                                                           |
| Real-time                         | WebSocket (FastAPI native)                                                                        |
| API contract                      | REST + OpenAPI schema (auto-generated by FastAPI); `openapi-typescript` for typed frontend client |
| Testing                           | pytest (backend unit/integration); Playwright (E2E)                                               |
| Local dev                         | docker-compose (FastAPI + PostgreSQL + Redis)                                                     |
| Cloud (Phase 4+)                  | Cloud Run (GCP) or ECS Fargate (AWS) for agent containers                                         |

**Note on GIL:** Agent work is I/O-bound (waiting on Claude API and Sleeper API). `asyncio` handles this correctly without free-threaded Python. Standard GIL-enabled Python 3.13 is the right choice.

---

## Project Structure

```
clanker-gauntlet/
├── CLAUDE.md
├── pyproject.toml
├── docker-compose.yml
├── config/
│   └── sports/
│       ├── nfl.yaml          # roster slots, scoring rules, stat field mappings
│       ├── nba.yaml
│       └── mlb.yaml
├── backend/
│   ├── api/                  # FastAPI routers (sessions, teams, decisions, ws)
│   ├── auth/                 # JWT auth, user accounts, API key storage
│   ├── core/
│   │   ├── event_runner.py   # advances event log, owns WorldState, resolves intentions
│   │   ├── session.py        # Session lifecycle (DRAFT → IN_PROGRESS → PAUSED → COMPLETED)
│   │   ├── scheduler.py      # APScheduler integration for MANAGED/IMMERSIVE modes
│   │   └── sport_config.py   # SportConfig loader from yaml
│   ├── league/
│   │   ├── engine.py         # scoring rules, matchup resolution
│   │   ├── roster.py         # roster state, lineup slots
│   │   ├── waivers.py        # FAAB sealed-bid auction resolution
│   │   ├── trades.py         # trade proposal, soft-locking, acceptance
│   │   └── standings.py      # win/loss, points, playoff picture
│   ├── teams/
│   │   ├── protocol.py       # Team abstract base (decide_lineup, bid_waivers, evaluate_trade)
│   │   ├── agent_team.py     # LLM-backed team (SingleAgent | ToolUseAgent | MultiAgentTeam)
│   │   ├── human_team.py     # UI-backed team (PendingDecision → user resolves via web UI)
│   │   └── external_team.py  # HTTP-backed team (user-uploaded container)
│   ├── agents/
│   │   ├── single.py         # one Claude call per decision
│   │   ├── tool_use.py       # reactive tool-use loop
│   │   ├── multi_agent.py    # Researcher → Analyst → Strategist pipeline
│   │   └── archetypes.py     # preset persona system prompts + tendencies
│   ├── data/
│   │   ├── providers/
│   │   │   ├── sleeper.py    # Sleeper API client (NFL stats, projections, players)
│   │   │   ├── balldontlie.py # NBA/MLB stats (free, no auth)
│   │   │   └── rss.py        # injury reports and news RSS feeds
│   │   ├── compiler.py       # ScriptCompiler: historical data → season_YYYY.events.jsonl
│   │   ├── live_ingester.py  # live season: real-time event ingestion pipeline
│   │   ├── cache.py          # disk cache layer (player universe, projections)
│   │   └── models.py         # Pydantic models: Player, Projection, NewsItem, GameEvent
│   └── db/
│       ├── base.py           # DeclarativeBase
│       ├── models.py         # all 20 SQLAlchemy ORM models + enums
│       └── session.py        # async engine + AsyncSessionLocal + get_db
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard/    # league standings, active sessions
│   │   │   ├── Session/      # live sim view, event timeline, scores
│   │   │   ├── Lineup/       # human lineup editor with countdown
│   │   │   ├── Waivers/      # FAAB bidding UI
│   │   │   ├── Trades/       # trade proposal and acceptance UI
│   │   │   ├── Agents/       # upload and manage agents
│   │   │   └── Account/      # user settings, API keys
│   │   ├── store/            # Zustand state (session state, pending decisions)
│   │   └── ws/               # WebSocket client, event handlers
│   └── vite.config.ts
├── agent-sdk/                # published separately; users implement this to build agents
│   ├── python/
│   │   ├── base_agent.py     # BaseFantasyAgent with HTTP server boilerplate
│   │   └── models.py         # WeekContext, LineupDecision, WaiverBid, TradeDecision
│   └── spec/
│       └── openapi.yaml      # formal HTTP protocol spec agents must implement
├── alembic/
│   ├── env.py                # Alembic migration environment
│   ├── script.py.mako        # migration template
│   └── versions/             # generated migration files
├── .github/
│   └── dependabot.yml        # weekly dep updates (pip, docker, actions)
└── tests/
    └── conftest.py           # async test client + DB fixtures
```

---

## Sessions

A session is a fully isolated league instance. Multiple sessions can run concurrently, each with its own agents, state, and time mode.

```
Session
├── id, name, sport, season
├── status: DRAFT → IN_PROGRESS → PAUSED → COMPLETED
├── script_speed: BLITZ | MANAGED | IMMERSIVE
├── compression_factor: N     (MANAGED only; e.g. 7 = 1 week per real day)
├── season_start_wall_time    (when the session clock began)
├── teams: [Team]             (AgentTeam | HumanTeam | ExternalTeam, up to 12)
├── event_log_path            (path to compiled .events.jsonl)
└── world_state               (rosters, FAAB balances, standings, scores)
```

### Session Membership

```
User
├── profile (email, password hash, display name)
├── api_keys (Anthropic key — encrypted at rest)
├── owned_sessions []
└── memberships [] ──► SessionMembership
                           ├── session_id
                           ├── role: OWNER | MEMBER | OBSERVER
                           └── team: HumanTeam | AgentTeam | ExternalTeam
```

- Sessions are **private by default**; members join via expiring invite link
- Each member controls exactly one team
- Observers have read-only access (no team)
- API keys are user-scoped; built-in agents use the member's own Anthropic key
- Session transparency is configurable: owners can allow all members to see all agent reasoning logs

---

## Script Speeds

The same compiled script is used for all three speeds. Only the mechanism that advances the cursor and handles agent decision windows differs.

| Speed       | Key         | Mechanism                                                                               | Use case                                                     |
| ----------- | ----------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `BLITZ`     | `blitz`     | Tight async loop; does not wait for agents; pre-loads context via lookahead             | Backtesting, agent tuning, research                          |
| `MANAGED`   | `managed`   | APScheduler at N:1 wall-clock ratio; blocks at each agent window until all teams submit | League with friends without a 17-week commitment             |
| `IMMERSIVE` | `immersive` | 1:1 wall-clock mapping; does not wait for agents; context arrives via live feed         | Full fantasy season experience; supports live-season scripts |

---

## Event Log

The season script is compiled once from data APIs and stored in the `season_events` DB table (shared across all sessions backtesting the same season). The EventRunner holds a cursor (`current_seq`) into this table, persisted in the `sessions` row so sessions survive restarts.

`STAT_UPDATE` events flow through Redis Streams only — they are NOT stored in `season_events`. All other event types are stored and drive the simulation.

### Event Types

```
ROSTER_LOCK          week N lineups lock
NEWS_ITEM            beat reporter item, player news
INJURY_UPDATE        player status change (ACTIVE | QUESTIONABLE | DOUBTFUL | OUT | IR)
AGENT_WINDOW_OPEN    agents/humans may submit a decision; carries deadline and type
AGENT_WINDOW_CLOSE   deadline reached; runner resolves all collected intentions
GAME_START           week N games begin
SCORE_UPDATE         player_id, fantasy_points (incremental or final)
WEEK_END             final scores locked, standings updated
WAIVER_OPEN          FAAB window opens
WAIVER_RESOLVED      bids processed, claims applied
TRADE_PROPOSED       offer from one team to another
TRADE_RESOLVED       accepted | rejected | expired
SEASON_END           final standings, playoff results
```

### Playback Controls (UI)

- **Play** — auto-advance cursor (respects compression factor or wall clock)
- **Pause** — stop advancing
- **Step** — advance one event
- **Seek** — jump to any week; reconstruct state from nearest snapshot + replay

Snapshots are taken at week boundaries to avoid replaying from week 1.

---

## Team Architecture

All team types implement the same interface. The EventRunner only calls these methods:

```python
class Team(Protocol):
    async def make_draft_pick(self, ctx: DraftContext) -> DraftPick: ...      # Phase 2
    async def decide_lineup(self, ctx: WeekContext) -> LineupDecision: ...
    async def bid_waivers(self, ctx: WaiverContext) -> list[WaiverBid]: ...
    async def evaluate_trade(self, ctx: TradeContext) -> TradeDecision: ...
```

### AgentTeam — LLM-backed

Configurable reasoning depth:

```
shallow       one Claude call, fast + cheap (Haiku)
              good for: low-stakes decisions, bulk simulation

standard      reactive tool-use loop (Haiku/Sonnet)
              agent queries projections, news, injuries explicitly

deep          multi-agent pipeline (Sonnet/Opus for key decisions)
              Researcher → Analyst → Strategist
```

**Multi-agent pipeline (deep mode):**

```
LineupDecision request
      │
      ▼
 Researcher   tool-use loop: queries projections, news, injury status
      │        returns structured intel report
      ▼
 Analyst      scores each roster option against intel; returns ranked options
      │        with confidence and reasoning
      ▼
 Strategist   makes final call; writes reasoning trace to decision log
```

The runner never sees this internal structure — it just awaits `decide_lineup()`.

### HumanTeam — UI-backed

```
AGENT_WINDOW_OPEN fires
      │
      └── HumanTeam creates PendingDecision in DB
          WebSocket push → UI shows "Action required" + countdown
          User submits via lineup editor / waiver UI / trade UI
          PendingDecision resolved → returned to runner
          Deadline passes with no action → auto-lineup applied
          (start highest-projected available players)
```

### ExternalTeam — container-backed

User-uploaded Docker image implementing the agent HTTP protocol. The runner calls into it via HTTP. Language-agnostic — users can write agents in any language.

---

## Agent HTTP Protocol (ExternalTeam / Agent SDK)

```
POST /lineup    WeekContext    → LineupDecision
POST /waiver    WaiverContext  → list[WaiverBid]
POST /trade     TradeContext   → TradeDecision
GET  /health                  → { status: "ok", agent_name: "..." }
```

Formal spec: `agent-sdk/spec/openapi.yaml`

Python SDK usage:

```python
from clanker_agent_sdk import BaseFantasyAgent, serve
from clanker_agent_sdk.models import WeekContext, LineupDecision, WaiverContext, WaiverBid, TradeContext, TradeDecision

class MyAgent(BaseFantasyAgent):
    async def decide_lineup(self, ctx: WeekContext) -> LineupDecision: ...
    async def bid_waivers(self, ctx: WaiverContext) -> list[WaiverBid]: ...
    async def evaluate_trade(self, ctx: TradeContext) -> TradeDecision: ...

if __name__ == "__main__":
    serve(MyAgent(), port=8080)
```

---

## Concurrency & Conflict Resolution

Agents run concurrently within each AGENT_WINDOW. Conflicts are resolved by the runner after all intentions are collected — never during submission.

### Waivers — FAAB Sealed-Bid Auction

All agents submit bids independently during the waiver window. At `AGENT_WINDOW_CLOSE`, the runner processes in one atomic DB transaction:

1. Sort all bids by FAAB amount descending
2. For each player (highest bid first): award to top bidder, deduct FAAB
3. If a team's top target is gone, process their next preference
4. Ties broken by waiver priority order

No jitter needed for correctness. Competing for the same player is a feature (highest bidder wins).

### Trades — Soft Locking

```
Trade proposed for Player X:
  → Player X flagged TRADE_LOCKED in DB
  → No other trade can include Player X while lock is held
  → If another agent tries to include X: rejected with PLAYER_IN_NEGOTIATION error
  → On resolution (accept | reject | deadline): lock released immediately
```

### Lineup Decisions

Fully parallel — each team's roster is independent, no conflicts possible.

### Jitter

Used only as a performance optimization to stagger Claude API and data API calls at `AGENT_WINDOW_OPEN`, preventing thundering herd / rate limit bursts. Has no effect on correctness or conflict resolution.

---

## Agent Archetypes

Built-in personas available to all users. Each defined by a system prompt + behavioral tendencies.

| Name              | Personality                                      |
| ----------------- | ------------------------------------------------ |
| The Analytician   | Purely projection-driven, ignores narrative      |
| The Contrarian    | Fades consensus, loves high-variance plays       |
| The Waiver Hawk   | Streams aggressively, roster always churning     |
| The Loyalist      | Slow to drop players, trusts track record        |
| The Newshound     | Reacts heavily to injury news and beat reporters |
| The Gambler       | Stacks offenses, shoots for ceiling not floor    |
| The Handcuff King | Rosters all backup RBs, plays it safe            |
| The Trader        | Constantly looking to buy low / sell high        |

Users can also define custom agents via a system prompt in the UI, or upload their own container.

---

## Data Sources

### Sleeper API (NFL primary)

- Base URL: `https://api.sleeper.app/v1`
- No auth required
- `GET /players/nfl` — full player universe (~300KB, cache to disk)
- `GET /stats/nfl/{season_type}/{season}/{week}` — weekly stats
- `GET /projections/nfl/{season_type}/{season}/{week}` — weekly projections
- `GET /players/nfl/trending/add` — trending waiver adds

### Ball Don't Lie (NBA / MLB)

- Free, no auth required
- NBA and MLB stats, players, game logs

### News / Injury Reports

- RotoBaller / Rotoworld RSS feeds
- NFL injury report (scraped or via aggregator)

### Script Compiler vs. Live Ingester

| Mode        | Component        | Behavior                                                                                                            |
| ----------- | ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| Backtesting | `ScriptCompiler` | One-time: pulls all historical data for a completed season → writes to `season_scripts` + `season_events` DB tables |
| Live season | `LiveIngester`   | Continuous: polls data APIs for new events as the real season progresses → appends rows to `season_events`          |

Both produce rows in the same `season_events` table consumed by the EventRunner.

---

## Database Schema

### Global / Shared (compiled once, referenced by many sessions)

```
season_scripts      id, sport, season, season_type, compiled_at, total_events, status
                    UNIQUE(sport, season, season_type)

season_events       id (bigint), script_id, seq, event_type, payload (JSONB),
                    week_number, sim_offset_hours
                    INDEX(script_id, seq), INDEX(script_id, week_number)
                    sim_offset_hours = hours from season kickoff; wall_time per session
                    computed as wall_start_time + (sim_offset_hours / compression_factor)
```

### Auth

```
users               id, email, password_hash (nullable), auth0_sub (nullable),
                    display_name, anthropic_api_key_enc (Fernet blob)

session_invites     id, session_id, token (unique), created_by, expires_at,
                    used_at, used_by
```

### Sessions

```
sessions            id, owner_id, script_id (FK season_scripts), name, sport, season,
                    status, mode, compression_factor, wall_start_time,
                    current_seq (EventRunner cursor), scoring_config (JSONB)
                    status: DRAFT_PENDING → DRAFT_IN_PROGRESS → DRAFT_COMPLETE
                            → IN_PROGRESS → PAUSED → COMPLETED

session_memberships id, session_id, user_id (nullable), role (OWNER|MEMBER|OBSERVER),
                    team_id (nullable — observers have no team)
                    UNIQUE(session_id, user_id)
```

### Teams & Rosters

```
teams               id, session_id, name, type (AGENT|HUMAN|EXTERNAL),
                    faab_balance, config (JSONB)
                    config shape: AGENT={archetype,reasoning_depth,system_prompt}
                                  EXTERNAL={container_url,health_endpoint}
                                  HUMAN={}

roster_players      id, team_id, player_id (Sleeper string ID), slot (ACTIVE|BENCH|IR),
                    acquired_week, acquired_via (DRAFT|WAIVER|TRADE)
                    UNIQUE(team_id, player_id)
                    Player metadata is never stored — always fetched from Sleeper/Redis
```

### Draft (schema present; logic wired in Phase 2)

```
drafts              id, session_id (unique), type (SNAKE|AUCTION), status,
                    current_round, current_pick, turn_team_id, pick_deadline,
                    auction_budget (nullable — separate from in-season FAAB)

draft_picks         id, draft_id, team_id, player_id, round, pick_number,
                    bid_amount (nullable, AUCTION only), picked_at
```

### Session Events & Decisions

```
processed_events    id, session_id, seq, event_type, payload (JSONB), processed_at
                    Per-session audit log of meaningful milestones ONLY.
                    STAT_UPDATE events flow through Redis Streams — not stored here.
                    Stored types: AGENT_WINDOW_*, WEEK_END, WAIVER_RESOLVED,
                    TRADE_RESOLVED, INJURY_UPDATE, DRAFT_PICK, SEASON_END

pending_decisions   id, session_id, team_id, decision_type, context (JSONB),
                    deadline, resolved_at, resolution (JSONB)
                    Open action waiting on a human; auto-resolved on deadline

agent_decisions     id, session_id, team_id, seq, decision_type, payload (JSONB),
                    reasoning_trace (text), tokens_used, created_at
                    Full audit of every decision by every team (agents + humans)
```

### League Engine

```
matchups            id, session_id, period_number, home_team_id, away_team_id,
                    home_score, away_score, winner_team_id (nullable)
                    Scores increment on each STAT_UPDATE; winner set at WEEK_END
                    Live standings = standings JOIN current matchup row

player_scores       id, session_id, team_id, period_number, player_id,
                    points_total, stats_json (JSONB), updated_at
                    Upserted on each STAT_UPDATE. stats_json holds raw accumulators
                    e.g. {"rec": 7, "rec_yd": 89, "rec_td": 1}
                    UNIQUE(session_id, team_id, period_number, player_id)

standings           id, session_id, team_id, wins, losses, ties,
                    points_for, points_against, updated_at
                    Season record only. Updated once per WEEK_END.
                    UNIQUE(session_id, team_id)

waiver_bids         id, session_id, team_id, period_number, add_player_id,
                    drop_player_id (nullable), bid_amount, priority,
                    status (PENDING|WON|LOST|CANCELLED), processed_at
                    priority = preference order (1 = top choice)
                    Resolved atomically at WAIVER_RESOLVED: highest bid wins

trade_proposals     id, session_id, proposing_team_id, receiving_team_id,
                    offered_player_ids (JSONB array), requested_player_ids (JSONB array),
                    status (PENDING|ACCEPTED|REJECTED|EXPIRED|CANCELLED),
                    proposed_at, resolved_at, note

trade_locks         player_id (PK), session_id (PK), trade_proposal_id, locked_until
                    Composite PK — a player can only be locked once per session
                    Released immediately on trade resolution
```

### Snapshots

```
snapshots           id, session_id, seq, period_number, world_state (JSONB), taken_at
                    Captured at each week boundary.
                    world_state: all rosters, FAAB balances, standings, matchup scores
                    Enables seek/resume without replaying from seq=0
```

### What Lives Outside the DB

```
Player universe     Sleeper API + Redis cache (name, position, NFL team, etc.)
Projections         Sleeper API + Redis cache
STAT_UPDATE events  Redis Streams only — play-by-play feel, not persisted to DB
Event distribution  Redis Streams  session:{id}:events
```

---

## State Persistence & Replay

- `season_events` is the source of truth (shared, immutable once compiled)
- WorldState at any point = nearest snapshot before that point + replay of `processed_events` since
- Snapshots taken automatically at week boundaries
- Cursor position (`current_seq`) persisted in `sessions` row — sessions survive server restarts
- Agent reasoning traces stored in `agent_decisions` per decision for full auditability in the UI

---

## Deployment

### Local (Phase 1–2)

```bash
docker-compose up
# spins up: backend, frontend, PostgreSQL, Redis
```

### Cloud (Phase 3+)

Same containers, different orchestration:

- Backend: Cloud Run / ECS / Kubernetes
- DB: PostgreSQL (RDS or Cloud SQL)
- Agent containers: user pushes to a registry; platform pulls and runs in isolation
- WebSocket: sticky sessions or a pub/sub layer (Redis) if horizontally scaled

---

## Scoring

- Default: **0.5 PPR**, standard NFL fantasy roster
- Roster: QB / 2 RB / 2 WR / TE / FLEX / K / DEF
- Configurable per session via `config/sports/nfl.yaml`
- Sport configs define roster slots, scoring rules, stat field mappings

---

## Development Phases

### Phase 1 — Foundation + Web UI + Tool-Use Agents

Backend and frontend built together for easier debugging and iteration.

**Backend**

- [x] FastAPI skeleton with PostgreSQL + Alembic + Redis
- [x] SQLAlchemy async models (20 tables) + initial migration applied
- [x] pydantic-settings Config with Auth0/JWT toggle via `AUTH_PROVIDER`
- [x] psycopg2-binary for Alembic sync driver; asyncpg for app async driver
- [x] Auth: Auth0 OIDC flow + JWT fallback via authlib; `get_current_user` dependency
- [x] Fernet encryption for user Anthropic API keys at rest
- [x] Sleeper API client + two-tier cache (disk for player universe, Redis for projections/stats)
- [x] Pydantic models: Player, PlayerStats, Projection, NewsItem, GameEvent, WaiverPlayer
- [x] Ruff + Prettier + pre-commit hooks
- [x] pytest suite: 166 tests (scoring engine, sport config, auth utils, auth endpoints, data models,
      world state, waiver resolution, event runner)
- [x] ScriptCompiler: pull 2025 NFL data → `season_scripts` + `season_events` DB
      (5,663 events: 5,526 SCORE_UPDATE + structural events across 17 weeks)
- [x] Scoring engine (0.5 PPR) — validated 0.00 delta vs Sleeper for all skill positions
- [x] EventRunner — BLITZ mode (cursor-based, batch fetch, per-event cursor persist)
      AGENT_WINDOW_OPEN launches asyncio Tasks; AGENT_WINDOW_CLOSE/WAIVER_RESOLVED collects them
      Three script speeds (on Session): BLITZ (no wait, lookahead context), MANAGED (block
      until all agents done), IMMERSIVE (no wait, live feed context). EventRunnerService is the
      shared singleton that manages all session tasks; one asyncio.Task per session.
- [x] `WorldState` — in-memory league state with snapshot serialization (to_snapshot/from_snapshot)
- [x] `BaseTeam` protocol — abstract interface (decide_lineup, bid_waivers, evaluate_trade)
- [x] `AgentTeam` + tool-use loop — context-scoped tools, archetype system prompt, decision logging
      Tools: view*my_roster, get_projections, get_recent_news, view_waiver_wire, submit*\*
- [x] 4 built-in archetype personas (Analytician, Contrarian, Waiver Hawk, Loyalist)
- [x] FAAB waiver resolution (atomic, sealed-bid; `backend/league/waivers.py`)
- [x] Priority waiver resolution (ordered claims, one per team per period, fallback to next choice)
- [x] Priority reset modes: rolling, season-long, weekly-standings (`WorldState`)
- [x] Multi-provider LLM support — `BaseLLMClient` ABC; `AnthropicClient`, `OpenAIClient`,
      `GeminiClient` in `backend/agents/llm_providers/`; `llm_factory.build_llm_client()`;
      per-provider model defaults by reasoning depth
- [x] `user_api_keys` table (replaces `anthropic_api_key_enc`); one row per (user, provider),
      Fernet-encrypted; PUT/DELETE /auth/me/api-key; GET /auth/me returns `has_keys` dict
- [x] League organizational layer — `League`, `LeagueMembership`, `LeagueInvite` models;
      auto-provisioned personal league on registration; 12+ endpoints (`backend/api/leagues.py`);
      manager transfer; email/username search + invite link flows; session creation policy
- [x] Session + membership CRUD — `POST /{league_id}/sessions`, `POST /{session_id}/join`,
      `POST /{session_id}/leave`; bot takeover on IN_PROGRESS leave; invite link generation + join
- [x] Trade soft-locking — `backend/league/trades.py` (acquire/release locks, expire stale,
      execute_roster_swap); `backend/api/trades.py` (propose, list, detail, respond, cancel);
      409 on conflicting locks; atomic lock+proposal creation via flush()
- [x] State persistence + week-boundary snapshots — `EventRunner._take_snapshot()` writes to DB;
      `EventRunnerService._load_world_state()` resumes from latest snapshot on restart
- [x] WebSocket — `WS /ws/sessions/{session_id}?token=<jwt>`; Redis XREAD with 500ms blocking;
      delivers `{type, seq, payload}` to connected clients in real time

**Frontend**

- [ ] React + Vite scaffold, Zustand store, WebSocket client
- [ ] Auth flow (Auth0 + JWT fallback)
- [ ] Dashboard: active sessions, standings
- [ ] Session view: live event timeline, scores, agent reasoning log
- [ ] Lineup editor (human players) with deadline countdown
- [ ] Waiver bidding UI (FAAB)
- [ ] Trade proposal + acceptance UI
- [ ] Account settings: API key management
- [ ] Playwright E2E skeleton

### Phase 2 — MANAGED Mode + Human Players + Multi-Agent

- [ ] `HumanTeam` + PendingDecision pattern (human decisions via UI)
- [ ] MANAGED script speed (APScheduler + Redis job store)
- [ ] Auto-lineup fallback on missed deadlines
- [ ] `MultiAgentTeam` — Researcher → Analyst → Strategist pipeline
- [ ] Jitter for API call staggering at AGENT_WINDOW_OPEN

### Phase 3 — External Agents + IMMERSIVE Mode

- [ ] Agent SDK (`clanker_agent_sdk` Python package, published separately)
- [ ] `ExternalTeam` — HTTP container protocol
- [ ] Agent upload (zip / Docker image) via UI
- [ ] IMMERSIVE script speed (1:1 wall-clock)
- [ ] LiveIngester — real-time data pipeline for live seasons

### Phase 4 — Cloud + Live Seasons

- [ ] Cloud Run (GCP) or ECS Fargate (AWS) deployment
- [ ] Live 2026 NFL season ingestion
- [ ] Public leaderboards (opt-in)
- [ ] Premium features (hosted compute for external agents)

---

## Environment Variables

```
# Database (async driver for app; Alembic derives sync URL automatically)
DATABASE_URL=postgresql+asyncpg://clanker:clanker@localhost:5432/clanker_gauntlet

# Redis
REDIS_URL=redis://localhost:6379

# Auth — set AUTH_PROVIDER to switch between strategies
AUTH_PROVIDER=auth0             # or: jwt
AUTH0_DOMAIN=...                # required if AUTH_PROVIDER=auth0
AUTH0_CLIENT_ID=...             # required if AUTH_PROVIDER=auth0
AUTH0_CLIENT_SECRET=...         # required if AUTH_PROVIDER=auth0
JWT_SECRET_KEY=...              # required if AUTH_PROVIDER=jwt

# Encryption
ENCRYPTION_KEY=...              # for encrypting user Anthropic API keys at rest

# Platform-level LLM fallback keys (used when user has no key set for that provider)
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
```

## Commands

```bash
# Install backend deps
uv add fastapi sqlalchemy[asyncio] alembic asyncpg psycopg2-binary pydantic \
       pydantic-settings anthropic httpx apscheduler redis authlib \
       passlib[bcrypt] python-multipart cryptography rich

# Start local dev stack (PostgreSQL + Redis via Docker, backend runs directly)
docker compose up -d

# Run DB migrations
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"

# Compile season script (one-time, pull 2025 NFL data)
python -m backend.data.compiler --sport nfl --season 2025

# Run backend dev server
uvicorn backend.main:app --reload

# Run frontend dev server
cd frontend && npm run dev

# Run backend tests
pytest

# Run Playwright E2E tests
cd frontend && npx playwright test
```

## Current Status (as of March 2026)

Phase 1 backend is complete. All infrastructure, auth, data layer, simulation engine, agent system, waiver resolution, league/session management, trade soft-locking, WebSocket, and multi-provider LLM support are implemented. Frontend not yet started.

**Remaining Phase 1 work:**

1. React + Vite frontend scaffold — the only remaining Phase 1 item

---

## Open Concerns

**Auth not yet integration-tested**
The auth endpoints (register → login → `/auth/me`) have been implemented but not exercised end-to-end against a running server with a real DB. Validate before the frontend lands — a broken auth flow will block everything else.

**`SessionMiddleware` secret key**
`SessionMiddleware` (required for the Auth0 callback flow) uses `JWT_SECRET_KEY`, which defaults to `"changeme"` in `.env.example`. Must be set to a real secret before any Auth0 flow. Not a blocker locally, but a sharp edge for new contributors or staging deployments.

**`data_cache/` not auto-created** _(documented in README)_
The Sleeper player universe disk cache (`data_cache/nfl_players.json`) is gitignored and only created on first run. New contributors on a clean clone will need to run the app once (or the ScriptCompiler) before the cache exists. README setup steps note this.

**Frontend is absent**
The backend is complete but has no UI consumer. End-to-end verification (agent decisions visible in UI, live score ticking) is blocked until the React + Vite frontend scaffold lands.

**Auth unit tests missing**
The test suite covers scoring, world state, waivers, and the event runner. Auth endpoints (register, login, `/auth/me`) have no tests. These should be added before the frontend ships to avoid shipping a broken auth flow.

---

## Working Conventions

- **CLAUDE.md is always kept current.** Update the phase checklist, open concerns, and notes whenever functionality is added or design decisions change — before committing.
- **No commit without ruff + Prettier passing.** Pre-commit hooks enforce this automatically.
- **Commit messages describe the why, not just the what.**
- **No DB migrations without reviewing the autogenerated diff.** Alembic autogenerate can miss things (renamed columns, changed constraints) — always read the generated file before applying.
- **Batch DB inserts.** Use `session.add_all(batch)` in chunks for bulk writes (ScriptCompiler, score updates). Never insert row-by-row in a loop.

---

## Notes

- Cache `GET /players/nfl` to disk (`data_cache/nfl_players.json`) — it's ~300KB and rarely changes mid-season. Disk cache survives Redis restarts.
- Use `claude-haiku-4-5` for routine decisions (lineup, waivers), `claude-sonnet-4-6` for trades and deep-mode multi-agent reasoning
- The 2025 NFL season is complete — use it for all Phase 1–3 development (deterministic, no live data dependency)
- Agent API calls are expensive at scale — implement a token budget per agent per week
- All agent decisions (payload + reasoning trace) must be logged for UI auditability
- `AUTH_PROVIDER=jwt` for local dev; `AUTH_PROVIDER=auth0` for hosted/production
