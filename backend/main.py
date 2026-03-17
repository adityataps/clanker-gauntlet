import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis as AsyncRedis
from starlette.middleware.sessions import SessionMiddleware

from backend.api.health import router as health_router
from backend.api.leagues import router as leagues_router
from backend.api.scripts import router as scripts_router
from backend.api.sessions import router as sessions_router
from backend.api.trades import router as trades_router
from backend.api.users import router as users_router
from backend.api.ws import router as ws_router
from backend.auth.router import router as auth_router
from backend.config import settings
from backend.core.runner_service import EventRunnerService
from backend.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────
    redis = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis
    app.state.runner_service = EventRunnerService(AsyncSessionLocal, redis=redis)
    logger.info("Redis connected; EventRunnerService ready")
    yield
    # ── Shutdown ───────────────────────────────────────────────────────────
    await redis.aclose()
    logger.info("Redis connection closed")


app = FastAPI(
    title="Clanker Gauntlet",
    description="Fantasy sports simulation platform — AI agents vs. humans",
    version="0.1.0",
    lifespan=lifespan,
)

# SessionMiddleware is required for the Auth0 OAuth callback flow
app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret_key)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(scripts_router)
app.include_router(auth_router)
app.include_router(leagues_router)
app.include_router(users_router)
app.include_router(sessions_router)
app.include_router(trades_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"message": "Clanker Gauntlet API"}
