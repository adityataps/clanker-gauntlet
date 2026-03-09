"""
Shared test fixtures.

Environment variables are set at module load time (before any backend
imports) so pydantic-settings picks them up correctly.

Requires a running PostgreSQL instance with the test database:
    docker exec <postgres-container> psql -U clanker -d clanker_gauntlet \
        -c "CREATE DATABASE clanker_gauntlet_test;"
"""

import os

# Must be set before backend modules are imported (pydantic-settings reads at import)
os.environ.setdefault("AUTH_PROVIDER", "jwt")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production-at-least-32-chars")
os.environ.setdefault("ENCRYPTION_KEY", "FPBVsaFx5DpsTUFGFR0dHy7RaXFV7tqWjwE3fj4z_rA=")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://clanker:clanker@localhost:5432/clanker_gauntlet_test"
)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import backend.db.session as db_session_module
from backend.db.base import Base
from backend.main import app

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Session-scoped setup: replace the app's engine with a NullPool test engine.
#
# NullPool creates a fresh connection per request and never reuses them,
# which avoids asyncpg "operation in progress" / "attached to different loop"
# errors that occur when pooled connections are shared across async tasks.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    Replace app engine with a NullPool test engine and create schema.
    Runs once per test session; drops schema on teardown.
    """
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    # Patch module-level engine and session factory used by get_db
    db_session_module.engine = test_engine
    db_session_module.AsyncSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


# ---------------------------------------------------------------------------
# Per-test DB session (for direct DB access in tests)
# ---------------------------------------------------------------------------


@pytest.fixture
async def db() -> AsyncSession:
    """Yields a session that rolls back after each test."""
    async with db_session_module.AsyncSessionLocal() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# HTTP clients
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db: AsyncSession):
    """
    HTTP client with get_db overridden to the per-test session.
    Use for tests that mix direct DB access with HTTP requests.
    """
    from backend.db.session import get_db

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def http_client():
    """
    HTTP client that uses the app's own get_db (patched to the test engine).
    Each request gets its own fresh NullPool connection — no sharing.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def clean_users():
    """Truncate users table after a test that writes user records."""
    yield
    async with db_session_module.AsyncSessionLocal() as session:
        await session.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        await session.commit()
