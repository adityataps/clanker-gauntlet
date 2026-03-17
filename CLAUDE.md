# Clanker Gauntlet

A fantasy sports simulation platform where AI agents and human players compete in fantasy leagues. Agents make autonomous roster decisions based on player projections and news feeds. Supports backtesting against historical seasons and real-time play alongside live NFL seasons.

---

## Terminology

| Term             | Definition                                                                                                                                                                                                                                                              |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Season**       | A real-world sports season. Not stored — source from which Scripts are compiled.                                                                                                                                                                                        |
| **Script**       | Compiled, chronological event list from a season. Stored in `season_scripts` + `season_events`. Shared across all sessions backtesting the same season. Two types: **post-season** (pre-compiled, any speed) and **live-season** (real-time ingestion, Immersive only). |
| **Session**      | A user-created league playback of a script. Multiple users each control one team. Multiple sessions can run the same script concurrently and independently.                                                                                                             |
| **Script Speed** | How fast a session plays back the script and handles agent decision windows.                                                                                                                                                                                            |
| **Waiver Mode**  | How contested player pickups are resolved each week.                                                                                                                                                                                                                    |

### Script Speeds

| Speed       | Key         | Mechanism                                                                               | Use case                                              |
| ----------- | ----------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `BLITZ`     | `blitz`     | Tight async loop; does not wait for agents; pre-loads context via lookahead             | Backtesting, agent tuning                             |
| `MANAGED`   | `managed`   | APScheduler at N:1 wall-clock ratio; blocks at each agent window until all teams submit | League with friends, compressed schedule              |
| `IMMERSIVE` | `immersive` | 1:1 wall-clock; does not wait for agents; context arrives via live feed                 | Full fantasy experience; supports live-season scripts |

### Waiver Modes

| Mode         | How it works                                                                                                                                          |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **FAAB**     | Sealed-bid auction. $100 seasonal budget, never resets. Highest bid wins; deducted permanently. Ties by waiver priority. Unlimited claims per period. |
| **Priority** | Ordered claims. Highest-priority team gets each player. Free. One successful claim per team per period.                                               |

#### Priority Reset Modes (Priority only)

| Reset                | Behavior                                                                            |
| -------------------- | ----------------------------------------------------------------------------------- |
| **Rolling**          | Claim winner drops to bottom of priority list.                                      |
| **Season-long**      | Set once at season start (e.g. reverse draft order), never changes.                 |
| **Weekly standings** | Re-ranked weekly: worst record → highest priority. Tiebreaker: fewer points scored. |

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

**Note on GIL:** Agent work is I/O-bound (Claude API + Sleeper API). Standard GIL-enabled Python 3.13 + asyncio is correct.

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
│   │   ├── runner_service.py # EventRunnerService singleton; manages per-session asyncio.Tasks
│   │   ├── team_factory.py   # loads Team rows → BaseTeam with three-tier key resolution
│   │   ├── scheduler.py      # APScheduler integration for MANAGED/IMMERSIVE modes
│   │   └── sport_config.py   # SportConfig loader from yaml
│   ├── league/
│   │   ├── engine.py         # scoring rules, matchup resolution
│   │   ├── roster.py         # roster state, lineup slots
│   │   ├── waivers.py        # FAAB sealed-bid auction resolution
│   │   ├── trades.py         # trade proposal, soft-locking, acceptance
│   │   └── standings.py      # win/loss, points, playoff picture
│   ├── teams/
│   │   ├── protocol.py       # BaseTeam abstract base (decide_lineup, bid_waivers, evaluate_trade)
│   │   ├── agent_team.py     # LLM-backed team (tool-use loop + archetype system prompt)
│   │   ├── human_team.py     # UI-backed team (PendingDecision → user resolves via web UI)
│   │   └── external_team.py  # HTTP-backed team (user-uploaded container)
│   ├── agents/
│   │   ├── llm_client.py     # BaseLLMClient ABC + response types
│   │   ├── llm_factory.py    # build_llm_client_for_agent() with three-tier key resolution
│   │   ├── key_resolver.py   # resolve_api_key(user_id|None, league_id, provider, db)
│   │   ├── model_defaults.py # per-provider model names by reasoning depth
│   │   ├── llm_providers/    # AnthropicClient, OpenAIClient, GeminiClient
│   │   └── archetypes.py     # preset persona system prompts + tendencies
│   ├── data/
│   │   ├── providers/
│   │   │   ├── sleeper.py    # Sleeper API client (NFL stats, projections, players)
│   │   │   ├── balldontlie.py # NBA/MLB stats (free, no auth)
│   │   │   └── rss.py        # injury reports and news RSS feeds
│   │   ├── compiler.py       # ScriptCompiler: historical data → season_events DB rows
│   │   ├── live_ingester.py  # live season: real-time event ingestion pipeline
│   │   ├── cache.py          # disk cache layer (player universe, projections)
│   │   └── models.py         # Pydantic models: Player, Projection, NewsItem, GameEvent
│   └── db/
│       ├── base.py           # DeclarativeBase
│       ├── models.py         # all SQLAlchemy ORM models + enums
│       └── session.py        # async engine + AsyncSessionLocal + get_db
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard/    # league standings, active sessions
│   │   │   ├── Session/      # live sim view, event timeline, scores
│   │   │   ├── Lineup/       # human lineup editor with deadline countdown
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
│   └── versions/             # generated migration files
└── tests/
    └── conftest.py           # async test client + DB fixtures
```

---

## Event Log

Compiled once per season into `season_events` (shared across all sessions). EventRunner holds a `current_seq` cursor persisted in the `sessions` row — sessions survive restarts.

`STAT_UPDATE` events flow through Redis Streams only — **not** stored in `season_events`.

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
- **Seek** — jump to any week; reconstruct from nearest snapshot + replay

---

## Team Architecture

All team types implement the same interface:

```python
class BaseTeam(Protocol):
    async def make_draft_pick(self, ctx: DraftContext) -> DraftPick: ...    # Phase 2
    async def decide_lineup(self, ctx: WeekContext) -> LineupDecision: ...
    async def bid_waivers(self, ctx: WaiverContext) -> list[WaiverBid]: ...
    async def evaluate_trade(self, ctx: TradeContext) -> TradeDecision: ...
```

### AgentTeam — LLM-backed

Configurable reasoning depth:

```
shallow   one Claude call, fast + cheap (Haiku)
standard  reactive tool-use loop (Haiku/Sonnet); agent queries projections/news/injuries
deep      multi-agent pipeline: Researcher → Analyst → Strategist (Sonnet/Opus)
```

### HumanTeam — UI-backed (Phase 2)

On `AGENT_WINDOW_OPEN`: creates `PendingDecision` in DB → WebSocket push → user acts via UI. Auto-lineup applied if deadline passes with no action.

### ExternalTeam — container-backed (Phase 3)

User-uploaded Docker image. Runner calls via HTTP. Language-agnostic.

---

## Agent HTTP Protocol (ExternalTeam / Agent SDK)

```
POST /lineup    WeekContext    → LineupDecision
POST /waiver    WaiverContext  → list[WaiverBid]
POST /trade     TradeContext   → TradeDecision
GET  /health                  → { status: "ok", agent_name: "..." }
```

Formal spec: `agent-sdk/spec/openapi.yaml`

---

## Three-Tier API Key Resolution

```
Tier 1 (user)    user_api_keys row for (user_id, provider) — best model available
Tier 2 (league)  league_api_keys row for (league_id, provider) — shared league key
Tier 3 (system)  env var (ANTHROPIC_API_KEY etc.) — capped to cheapest model
```

`resolve_api_key(user_id: UUID | None, league_id, provider, db)` — pass `user_id=None` for agent-only teams (skips tier 1).

---

## Concurrency & Conflict Resolution

Agents run concurrently within each `AGENT_WINDOW`. Conflicts resolved atomically by the runner after all intentions collected.

**Waivers:** At `AGENT_WINDOW_CLOSE` — sort bids descending by FAAB, award highest bidder per player, deduct balance, cascade to next preference if top target gone. Ties by waiver priority.

**Trades:** Player locked in `trade_locks` on proposal. Any competing proposal including that player is rejected (`PLAYER_IN_NEGOTIATION`). Lock released immediately on resolution.

**Lineup decisions:** Fully parallel — each team's roster is independent.

**Jitter:** Staggered API calls at `AGENT_WINDOW_OPEN` only — prevents thundering herd. No effect on correctness.

---

## Agent Archetypes

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

Users can define custom agents via system prompt in the UI, or upload their own container.

---

## Data Sources

**Sleeper API** (NFL primary, no auth): `https://api.sleeper.app/v1`

- `GET /players/nfl` — full player universe (~300KB, cache to disk)
- `GET /stats/nfl/{season_type}/{season}/{week}` — weekly stats
- `GET /projections/nfl/{season_type}/{season}/{week}` — weekly projections
- `GET /players/nfl/trending/add` — trending waiver adds

**Ball Don't Lie** (NBA/MLB, free, no auth) — stats, players, game logs

**News:** RotoBaller / Rotoworld RSS feeds

**ScriptCompiler** (backtesting): one-time pull → `season_scripts` + `season_events`
**LiveIngester** (live season): continuous poll → appends to `season_events`

---

## Database Schema

### Global / Shared

```
season_scripts      id, sport, season, season_type, compiled_at, total_events, status
                    UNIQUE(sport, season, season_type)

season_events       id (bigint), script_id, seq, event_type, payload (JSONB),
                    week_number, sim_offset_hours
                    INDEX(script_id, seq), INDEX(script_id, week_number)
                    wall_time per session = wall_start_time + (sim_offset_hours / compression_factor)
```

### Auth

```
users               id, email, password_hash (nullable), auth0_sub (nullable), display_name

user_api_keys       id, user_id, provider, encrypted_key (Fernet), created_at
                    UNIQUE(user_id, provider)

league_api_keys     id, league_id, provider, encrypted_key (Fernet), created_at
                    UNIQUE(league_id, provider)

session_invites     id, session_id, token (unique), created_by, expires_at, used_at, used_by
```

### Sessions

```
sessions            id, owner_id, script_id, name, sport, season, status, script_speed,
                    waiver_mode, compression_factor, wall_start_time, current_seq,
                    scoring_config (JSONB)
                    status: DRAFT_PENDING → IN_PROGRESS → PAUSED → COMPLETED

session_memberships id, session_id, user_id (nullable), role (OWNER|MEMBER|OBSERVER),
                    team_id (nullable — observers have no team)
                    UNIQUE(session_id, user_id)
```

### League

```
leagues             id, owner_id, name, description, sport, session_creation, allow_shared_key,
                    created_at

league_memberships  id, league_id, user_id, role (MANAGER|MEMBER), status (ACTIVE|INVITED),
                    joined_at

league_invites      id, league_id, token (unique), created_by, expires_at, used_at, used_by
```

### Teams & Rosters

```
teams               id, session_id, name, type (AGENT|HUMAN|EXTERNAL), faab_balance,
                    config (JSONB)
                    config: AGENT={archetype, reasoning_depth, provider, system_prompt}
                            EXTERNAL={container_url, health_endpoint}
                            HUMAN={}

roster_players      id, team_id, player_id (Sleeper string ID), slot (ACTIVE|BENCH|IR),
                    acquired_week, acquired_via (DRAFT|WAIVER|TRADE)
                    UNIQUE(team_id, player_id)
                    Player metadata never stored — always fetched from Sleeper/Redis
```

### Draft (schema present; logic wired in Phase 2)

```
drafts              id, session_id (unique), type (SNAKE|AUCTION), status,
                    current_round, current_pick, turn_team_id, pick_deadline,
                    auction_budget (nullable)

draft_picks         id, draft_id, team_id, player_id, round, pick_number,
                    bid_amount (nullable, AUCTION only), picked_at
```

### Session Events & Decisions

```
processed_events    id, session_id, seq, event_type, payload (JSONB), processed_at
                    Per-session audit log. STAT_UPDATE via Redis Streams only.
                    Stored: AGENT_WINDOW_*, WEEK_END, WAIVER_RESOLVED, TRADE_RESOLVED,
                    INJURY_UPDATE, DRAFT_PICK, SEASON_END

pending_decisions   id, session_id, team_id, decision_type, context (JSONB),
                    deadline, resolved_at, resolution (JSONB)
                    Open action waiting on a human; auto-resolved on deadline

agent_decisions     id, session_id, team_id, seq, decision_type, payload (JSONB),
                    reasoning_trace (text), tokens_used, created_at
                    Full audit of every decision (agents + humans)
```

### League Engine

```
matchups            id, session_id, period_number, home_team_id, away_team_id,
                    home_score, away_score, winner_team_id (nullable)
                    Scores increment on STAT_UPDATE; winner set at WEEK_END

player_scores       id, session_id, team_id, period_number, player_id,
                    points_total, stats_json (JSONB), updated_at
                    Upserted on each STAT_UPDATE  e.g. {"rec": 7, "rec_yd": 89, "rec_td": 1}
                    UNIQUE(session_id, team_id, period_number, player_id)

standings           id, session_id, team_id, wins, losses, ties, points_for, points_against
                    Updated once per WEEK_END. UNIQUE(session_id, team_id)

waiver_bids         id, session_id, team_id, period_number, add_player_id,
                    drop_player_id (nullable), bid_amount, priority,
                    status (PENDING|WON|LOST|CANCELLED), processed_at

trade_proposals     id, session_id, proposing_team_id, receiving_team_id,
                    offered_player_ids (JSONB), requested_player_ids (JSONB),
                    status (PENDING|ACCEPTED|REJECTED|EXPIRED|CANCELLED),
                    proposed_at, resolved_at, note

trade_locks         player_id (PK), session_id (PK), trade_proposal_id, locked_until
                    Composite PK. Released immediately on trade resolution.
```

### Snapshots

```
snapshots           id, session_id, seq, period_number, world_state (JSONB), taken_at
                    Captured at week boundaries. Enables seek/resume without seq=0 replay.
                    world_state: all rosters, FAAB balances, standings, matchup scores
```

### What Lives Outside the DB

```
Player universe     Sleeper API + Redis cache
Projections         Sleeper API + Redis cache
STAT_UPDATE events  Redis Streams only (session:{id}:events)
```

---

## Scoring

- Default: **0.5 PPR**, standard NFL fantasy roster
- Roster: QB / 2 RB / 2 WR / TE / FLEX / K / DEF
- Configurable via `config/sports/nfl.yaml`

---

## Development Phases

### Phase 1 — Foundation + Web UI + Tool-Use Agents ✓ (backend complete)

**Backend — complete.** Key components:

- FastAPI + PostgreSQL + Alembic + Redis; 20 ORM models; async + migration stack
- Auth0 OIDC + JWT fallback; Fernet-encrypted API keys; `user_api_keys` multi-provider table
- Multi-provider LLM: `BaseLLMClient` ABC; Anthropic/OpenAI/Gemini providers; three-tier key resolution
- Sleeper API client + two-tier cache (disk for player universe, Redis for projections/stats)
- ScriptCompiler: 2025 NFL → 5,663 events (17 weeks)
- Scoring engine: 0.5 PPR validated 0.00 delta vs Sleeper
- EventRunner: BLITZ mode, cursor-based, batch fetch, per-event cursor persist; broadcasts all events to Redis Stream `session:{id}:events`
- WorldState: in-memory league state, snapshot serialization
- AgentTeam: tool-use loop, archetype system prompts, decision logging
- 4 built-in archetypes (Analytician, Contrarian, Waiver Hawk, Loyalist)
- FAAB + Priority waiver resolution (atomic, sealed-bid; all reset modes)
- Trade soft-locking (acquire/release, 409 on conflict, atomic lock+proposal)
- Week-boundary snapshots written to DB; EventRunnerService resumes from latest snapshot
- League organizational layer: League/LeagueMembership/LeagueInvite; 12+ endpoints; invite flows
- Session + membership CRUD: join/leave/bot-takeover; session lifecycle (start/pause/get)
- WebSocket: `WS /ws/sessions/{id}?token=<jwt>`; Redis XREAD; delivers `{type, seq, payload}`
- pytest suite: 166 tests

**Frontend — in progress.**

- [x] React + Vite scaffold; Zustand store; WebSocket client
- [x] Auth flow (JWT; Auth0 hookup pending); `initAuth()` validates stored token on startup
- [x] Dashboard: active sessions, standings (mock data)
- [x] Lineup editor: slot defs, click-to-swap, auto-save with debounce
- [ ] Session view: live event timeline, scores, agent reasoning log
- [ ] Waiver bidding UI (FAAB)
- [ ] Trade proposal + acceptance UI
- [ ] Account settings: API key management
- [ ] Playwright E2E skeleton
- [ ] Replace mock data with real API calls

### Phase 2 — MANAGED Mode + Human Players + Multi-Agent

- [ ] `HumanTeam` + PendingDecision pattern
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
DATABASE_URL=postgresql+asyncpg://clanker:clanker@localhost:5432/clanker_gauntlet
REDIS_URL=redis://localhost:6379

AUTH_PROVIDER=jwt             # or: auth0
AUTH0_DOMAIN=...              # required if AUTH_PROVIDER=auth0
AUTH0_CLIENT_ID=...           # required if AUTH_PROVIDER=auth0
AUTH0_CLIENT_SECRET=...       # required if AUTH_PROVIDER=auth0
JWT_SECRET_KEY=...            # required always (also used by SessionMiddleware)

ENCRYPTION_KEY=...            # Fernet key for encrypting API keys at rest

# Platform-level LLM fallback (used when user/league has no key for that provider)
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
```

## Commands

```bash
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

Phase 1 backend is complete. Frontend scaffold, auth flow, dashboard, and lineup editor are built; remaining frontend pages (session view, waivers, trades, account) and real API wiring are next.

---

## Open Concerns

**Auth not yet integration-tested end-to-end**
Register → login → `/auth/me` implemented but not exercised against a real running server + DB. Validate before wiring remaining frontend pages.

**`SessionMiddleware` secret key**
Uses `JWT_SECRET_KEY` (defaults to `"changeme"` in `.env.example`). Must be a real secret before any Auth0 flow.

**`data_cache/` not auto-created**
`data_cache/nfl_players.json` is gitignored and only created on first run. New contributors need to run the app or ScriptCompiler once before the cache exists.

**Auth unit tests missing**
Register/login/`/auth/me` endpoints have no tests. Add before shipping frontend auth flow.

---

## Working Conventions

- **CLAUDE.md is always kept current.** Update phase checklist, open concerns, and notes before committing.
- **No commit without ruff + Prettier passing.** Pre-commit hooks enforce this automatically.
- **Commit messages describe the why, not just the what.**
- **No DB migrations without reviewing the autogenerated diff.** Alembic can miss renamed columns and changed constraints — always read before applying.
- **Batch DB inserts.** Use `session.add_all(batch)` in chunks. Never insert row-by-row in a loop.

---

## Notes

- Cache `GET /players/nfl` to disk (`data_cache/nfl_players.json`) — ~300KB, rarely changes. Disk cache survives Redis restarts.
- Use `claude-haiku-4-5` for routine decisions (lineup, waivers); `claude-sonnet-4-6` for trades and deep multi-agent reasoning.
- The 2025 NFL season is complete — use it for all Phase 1–3 development (deterministic, no live data dependency).
- Agent API calls are expensive at scale — implement a token budget per agent per week.
- All agent decisions (payload + reasoning trace) must be logged for UI auditability.
- `AUTH_PROVIDER=jwt` for local dev; `AUTH_PROVIDER=auth0` for hosted/production.
