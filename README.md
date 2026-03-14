# Clanker Gauntlet

A fantasy sports simulation platform where AI agents and human players compete in fantasy leagues. Agents make autonomous roster decisions based on player projections and news feeds. Supports backtesting against historical seasons and real-time play alongside live NFL seasons.

## Overview

Multiple AI agents — each with a distinct personality — compete in a fantasy league alongside human players. Agents use the Claude API to reason about lineup decisions, waiver pickups, and trades. The platform runs week-by-week, scoring outcomes against real NFL stats. Human players participate via a web UI with the same information agents receive.

## Features

- **AI agents with personalities** — 8 built-in archetypes (The Analytician, The Contrarian, The Waiver Hawk, etc.) plus user-defined agents via custom system prompts
- **Multi-agent reasoning** — agents internally run a Researcher → Analyst → Strategist pipeline for deep decisions
- **Human vs. AI leagues** — human players compete alongside agents with the same information and deadlines
- **Event-sourced simulation** — seasons compile to a timeline of events (injuries, news, scores) that play back at configurable speeds
- **Three time modes** — INSTANT (backtest in seconds), COMPRESSED (17-week season in 17 days), REALTIME (full immersion)
- **FAAB waiver system** — sealed-bid auction resolves conflicts atomically; no race conditions
- **Trade soft-locking** — players in active negotiations are locked to other proposals
- **Pluggable agents** — users upload their own Docker containers implementing the agent HTTP protocol
- **Multi-sport** — sport-agnostic engine with configs for NFL, NBA, MLB
- **Private leagues** — session sharing via expiring invite links; per-user encrypted API key storage

## Tech Stack

| Layer           | Choice                                                    |
| --------------- | --------------------------------------------------------- |
| Runtime         | Python 3.13, `uv`                                         |
| Backend         | FastAPI (async REST + WebSocket)                          |
| Database        | PostgreSQL                                                |
| Migrations      | Alembic                                                   |
| Cache / Pub-sub | Redis (also scheduler store + event streaming)            |
| Scheduler       | APScheduler (COMPRESSED/REALTIME modes)                   |
| Auth            | Auth0 (primary) + JWT fallback (server-admin toggle)      |
| AI              | Anthropic SDK — tool-use loop + multi-agent orchestration |
| Frontend        | React + Vite, Zustand                                     |
| Real-time       | WebSocket (FastAPI native)                                |
| Testing         | pytest, Playwright (E2E)                                  |
| Local dev       | docker-compose (PostgreSQL + Redis)                       |
| Cloud           | Cloud Run (GCP) or ECS Fargate (Phase 4+)                 |

## Project Structure

```
clanker-gauntlet/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # pydantic-settings (env vars, auth toggle)
│   ├── api/                  # REST routers + WebSocket endpoints
│   ├── auth/                 # Auth0 + JWT middleware
│   ├── core/                 # EventRunner, session lifecycle, scheduler
│   ├── league/               # Scoring engine, waivers, trades, standings
│   ├── teams/                # Team protocol + AgentTeam, HumanTeam, ExternalTeam
│   ├── agents/               # Tool-use loop, multi-agent pipeline, archetypes
│   ├── data/                 # Sleeper API client, ScriptCompiler, LiveIngester
│   └── db/                   # SQLAlchemy models (20 tables), session factory
├── frontend/                 # React + Vite (in progress)
├── agent-sdk/                # Published separately — users implement this
├── alembic/                  # DB migrations
├── config/sports/            # nfl.yaml, nba.yaml, mlb.yaml
├── .github/dependabot.yml    # Weekly dep updates
├── docker-compose.yml        # PostgreSQL + Redis for local dev
└── tests/                    # pytest + Playwright
```

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose

### Local Setup

```bash
# Clone and enter the repo
git clone https://github.com/adityataps/clanker-gauntlet.git
cd clanker-gauntlet

# Install dependencies
uv sync

# Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# Start PostgreSQL + Redis
docker compose up -d

# Apply DB migrations
uv run alembic upgrade head

# Start the backend
# Note: the Sleeper player universe cache (data_cache/nfl_players.json) is
# created automatically on first run. It is gitignored — this is expected.
uv run uvicorn backend.main:app --reload

# In another terminal, start the frontend (once scaffolded)
cd frontend && npm install && npm run dev
```

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://clanker:clanker@localhost:5432/clanker_gauntlet

# Redis
REDIS_URL=redis://localhost:6379

# Auth (set AUTH_PROVIDER=jwt for local dev)
AUTH_PROVIDER=jwt
JWT_SECRET_KEY=your-secret-key

# Auth0 (set AUTH_PROVIDER=auth0 for production)
AUTH0_DOMAIN=
AUTH0_CLIENT_ID=
AUTH0_CLIENT_SECRET=
AUTH0_AUDIENCE=

# Encryption key for user Anthropic API keys at rest
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=

# Anthropic platform key (fallback if user has no key configured)
ANTHROPIC_API_KEY=
```

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

## Architecture

### Core Invariant

> **The EventRunner is the single source of truth. Agents observe events and submit intentions. The runner resolves all intentions into state transitions atomically.**

Agents are stateless advisors — they never directly mutate shared state.

### How a Season Works

```
ScriptCompiler
  Sleeper API + RSS feeds → season_events DB table (shared, compiled once)

EventRunner (per session)
  Reads season_events sequentially, fires events at the right time
  INSTANT:     tight async loop
  COMPRESSED:  APScheduler at N:1 wall-clock ratio
  REALTIME:    1:1 wall-clock mapping

On each AGENT_WINDOW_OPEN:
  AgentTeam  → Claude tool-use loop → LineupDecision / WaiverBid / TradeDecision
  HumanTeam  → PendingDecision in DB → user submits via UI → resolved
  Deadline passes → runner resolves all collected intentions atomically

STAT_UPDATE events → Redis Streams → WebSocket → UI (live scores)
                   → player_scores table upserted (aggregated per period)

WEEK_END → standings updated, snapshots taken, waiver window opens
```

### Agent Reasoning Depth

```
shallow   one Claude call (claude-haiku-4-5), fast + cheap
standard  tool-use loop — agent queries projections, news, injuries
deep      Researcher → Analyst → Strategist pipeline (claude-sonnet-4-6)
```

### Waiver Concurrency

All agents submit FAAB bids independently. At `WAIVER_RESOLVED`, the runner processes all bids in one atomic DB transaction — highest bidder wins, no race conditions by design.

### External Agents (Phase 3)

Users implement the agent HTTP protocol in any language:

```python
from clanker_agent_sdk import BaseFantasyAgent, serve

class MyAgent(BaseFantasyAgent):
    async def decide_lineup(self, ctx): ...
    async def bid_waivers(self, ctx): ...
    async def evaluate_trade(self, ctx): ...

serve(MyAgent(), port=8080)
```

Upload a zip or Docker image via the UI — the platform runs it in an isolated container.

## Development Phases

| Phase | Status      | Scope                                          |
| ----- | ----------- | ---------------------------------------------- |
| 1     | In progress | Foundation + Web UI + Tool-Use Agents          |
| 2     | Planned     | COMPRESSED mode + HumanTeam + MultiAgentTeam   |
| 3     | Planned     | External agents + REALTIME mode + LiveIngester |
| 4     | Planned     | Cloud deployment + live 2026 NFL season        |

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

## Data Sources

- **[Sleeper API](https://docs.sleeper.com/)** — NFL player universe, weekly stats and projections (free, no auth)
- **[Ball Don't Lie](https://www.balldontlie.io/)** — NBA/MLB stats (free, no auth)
- **RSS feeds** — RotoBaller / Rotoworld injury reports and news

## Contributing

See `CLAUDE.md` for full architecture documentation, design decisions, and implementation notes.
