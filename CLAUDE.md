# Clanker Gauntlet

A fantasy sports simulation platform where AI agents and human players compete in fantasy leagues. Agents make autonomous roster decisions based on player projections and news feeds. Supports backtesting against historical seasons and real-time play alongside live NFL seasons.

---

## Vision

Multiple AI agents — each with a distinct personality — compete in a fantasy league alongside human players. Agents use the Claude API to reason about lineup decisions, waiver pickups, and trades. The platform runs week-by-week, scoring outcomes against real NFL stats. Human players participate via a web UI with the same information agents receive.

---

## Core Invariant

> **The EventRunner is the single source of truth. Agents observe events and submit intentions. The runner resolves all intentions into state transitions atomically.**

Agents are stateless advisors. They never directly mutate shared state.

---

## Tech Stack

- **Python 3.13** with `uv` for dependency management
- **FastAPI** — async REST API + WebSocket streaming
- **SQLAlchemy + Alembic** — ORM + migrations (SQLite locally, PostgreSQL in production)
- **APScheduler** — wall-clock event scheduling for COMPRESSED and REALTIME time modes
- **Anthropic SDK** (`anthropic`) — agent reasoning (tool-use loops, multi-agent orchestration)
- **Pydantic** — data models and validation throughout
- **Docker / docker-compose** — agent container isolation and local development
- **React + Vite** — web frontend
- **Zustand** — frontend simulation state management
- **Rich** — CLI output for development and debugging

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
│   │   ├── scheduler.py      # APScheduler integration for COMPRESSED/REALTIME modes
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
│       ├── models.py         # SQLAlchemy ORM models
│       └── migrations/       # Alembic migration scripts
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
└── tests/
```

---

## Sessions

A session is a fully isolated league instance. Multiple sessions can run concurrently, each with its own agents, state, and time mode.

```
Session
├── id, name, sport, season
├── status: DRAFT → IN_PROGRESS → PAUSED → COMPLETED
├── mode: INSTANT | COMPRESSED | REALTIME
├── compression_factor: N     (COMPRESSED only; e.g. 7 = 1 week per real day)
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

## Time Modes

The same compiled event log is used for all three modes. Only the mechanism that advances the cursor differs.

| Mode | Mechanism | Use case |
|------|-----------|----------|
| `INSTANT` | Tight async loop, advances as fast as the runner can process | Backtesting, agent tuning, research |
| `COMPRESSED` | APScheduler maps events to wall-clock time via compression factor | League with friends without a 5-month commitment (e.g. 17-week season in 17 days) |
| `REALTIME` | 1:1 wall-clock mapping to historical event timestamps | Immersive; feels like a real fantasy season |

---

## Event Log

The season script is a chronologically ordered JSONL file compiled once from data APIs. The EventRunner holds a cursor into this log.

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

All team types implement the same interface. The EventRunner only calls these three methods:

```python
class Team(Protocol):
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

| Name | Personality |
|------|-------------|
| The Analytician | Purely projection-driven, ignores narrative |
| The Contrarian | Fades consensus, loves high-variance plays |
| The Waiver Hawk | Streams aggressively, roster always churning |
| The Loyalist | Slow to drop players, trusts track record |
| The Newshound | Reacts heavily to injury news and beat reporters |
| The Gambler | Stacks offenses, shoots for ceiling not floor |
| The Handcuff King | Rosters all backup RBs, plays it safe |
| The Trader | Constantly looking to buy low / sell high |

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

| Mode | Component | Behavior |
|------|-----------|----------|
| Backtesting | `ScriptCompiler` | One-time: pulls all historical data for a completed season → `season_YYYY.events.jsonl` |
| Live season | `LiveIngester` | Continuous: polls data APIs for new events as the real season progresses → appends to event log |

Both produce the same event log format consumed by the EventRunner.

---

## Database Schema (simplified)

```
users               id, email, password_hash, display_name, anthropic_api_key_enc
sessions            id, owner_id, sport, season, mode, compression_factor, status, config_json
session_memberships session_id, user_id, role, team_id
teams               id, session_id, name, type (AGENT|HUMAN|EXTERNAL), config_json
event_log           id, session_id, seq, event_type, payload_json, wall_time
snapshots           id, session_id, seq, world_state_json, taken_at
pending_decisions   id, session_id, team_id, decision_type, context_json, deadline, resolved_at
agent_decisions     id, session_id, seq, team_id, decision_type, payload_json, reasoning_trace
trade_locks         player_id, session_id, trade_id, locked_until
```

---

## State Persistence & Replay

- The event log is append-only and is the source of truth
- WorldState at any point = nearest snapshot before that point + replay of events since
- Snapshots taken automatically at week boundaries
- Cursor position (current_seq) persisted in DB — sessions survive server restarts
- Agent reasoning traces stored per decision for full auditability in the UI

---

## Deployment

### Local (Phase 1–2)

```bash
docker-compose up
# spins up: backend, frontend, agent containers, SQLite
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

### Phase 1 — Foundation
- [ ] `backend/` FastAPI skeleton + SQLAlchemy models + Alembic
- [ ] Auth (JWT, user accounts, encrypted API key storage)
- [ ] Sleeper API client + disk cache
- [ ] Pydantic models: Player, Projection, NewsItem, GameEvent
- [ ] ScriptCompiler: pull 2025 NFL data → `.events.jsonl`
- [ ] Basic scoring engine (PPR)

### Phase 2 — EventRunner + Agents
- [ ] EventRunner with INSTANT mode (cursor + tight loop)
- [ ] `Team` protocol + `AgentTeam` (standard / tool-use depth)
- [ ] 4 archetype personas
- [ ] Single-session CLI runner end-to-end (no UI yet)
- [ ] State persistence + snapshots

### Phase 3 — Web UI + Human Players
- [ ] React + Vite frontend scaffold
- [ ] WebSocket state streaming from EventRunner to UI
- [ ] `HumanTeam` + PendingDecision pattern
- [ ] Lineup editor, waiver bidding UI, trade UI
- [ ] COMPRESSED time mode (APScheduler)
- [ ] Session invites and membership

### Phase 4 — Multi-agent + External Agents
- [ ] `MultiAgentTeam` (Researcher → Analyst → Strategist)
- [ ] Agent SDK (`clanker_agent_sdk` Python package)
- [ ] `ExternalTeam` (HTTP container protocol)
- [ ] Agent upload (zip / container image) via UI
- [ ] REALTIME time mode + LiveIngester

### Phase 5 — Cloud + Live Seasons
- [ ] PostgreSQL support
- [ ] Multi-user cloud deployment
- [ ] Live season ingestion (2026 NFL or NBA)
- [ ] Public leaderboards (opt-in)
- [ ] Premium features (hosted compute for external agents)

---

## Environment Variables

```
ANTHROPIC_API_KEY=...         # platform key (used if user has no key set)
DATABASE_URL=...              # sqlite:///./dev.db or postgresql://...
SECRET_KEY=...                # JWT signing key
ENCRYPTION_KEY=...            # for user API key encryption at rest
```

## Commands

```bash
# Install backend deps
uv add fastapi sqlalchemy alembic pydantic anthropic httpx apscheduler rich

# Run dev stack
docker-compose up

# Compile season script (one-time)
python -m clanker_gauntlet.data.compiler --sport nfl --season 2025

# Run single-session instant backtest (Phase 2 CLI)
python -m clanker_gauntlet.simulation.runner --season 2025 --mode instant --agents 8

# Run DB migrations
alembic upgrade head
```

## Notes

- Cache `GET /players/nfl` to disk — it's ~300KB and rarely changes mid-season
- Use `claude-haiku-4-5` for routine decisions (lineup, waivers), `claude-sonnet-4-6` for trades and deep-mode multi-agent reasoning
- The 2025 NFL season is complete — use it for all Phase 1–3 development (deterministic, no live data dependency)
- Agent API calls are expensive at scale — implement a token budget per agent per week
- All agent decisions (payload + reasoning trace) must be logged for UI auditability
