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

| Layer | Choice |
|-------|--------|
| Runtime | Python 3.13, `uv` |
| Backend | FastAPI (async REST + WebSocket) |
| Database | PostgreSQL |
| Migrations | Alembic |
| Cache / Pub-sub | Redis (also scheduler store + event streaming) |
| Scheduler | APScheduler (COMPRESSED/REALTIME modes) |
| Auth | Auth0 (primary) + JWT fallback (server-admin toggle) |
| AI | Anthropic SDK — tool-use loop + multi-agent orchestration |
| Frontend | React + Vite, Zustand |
| Real-time | WebSocket (FastAPI native) |
| Testing | pytest, Playwright (E2E) |
| Local dev | docker-compose (PostgreSQL + Redis) |
| Cloud | Cloud Run (GCP) or ECS Fargate (Phase 4+) |

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

# Encryption key for user Anthropic API keys at rest
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=

# Anthropic platform key (fallback if user has no key configured)
ANTHROPIC_API_KEY=
```

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

| Phase | Status | Scope |
|-------|--------|-------|
| 1 | In progress | Foundation + Web UI + Tool-Use Agents |
| 2 | Planned | COMPRESSED mode + HumanTeam + MultiAgentTeam |
| 3 | Planned | External agents + REALTIME mode + LiveIngester |
| 4 | Planned | Cloud deployment + live 2026 NFL season |

## Agent Archetypes

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

## Data Sources

- **[Sleeper API](https://docs.sleeper.com/)** — NFL player universe, weekly stats and projections (free, no auth)
- **[Ball Don't Lie](https://www.balldontlie.io/)** — NBA/MLB stats (free, no auth)
- **RSS feeds** — RotoBaller / Rotoworld injury reports and news

## Contributing

See `CLAUDE.md` for full architecture documentation, design decisions, and implementation notes.
