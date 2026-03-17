"""
Shared FastAPI dependencies.

Usage:
    from backend.api.deps import get_runner_service, get_redis

    @router.post("/sessions/{session_id}/start")
    async def start_session(
        session_id: str,
        runner: EventRunnerService = Depends(get_runner_service),
    ): ...
"""

from fastapi import Request
from redis.asyncio import Redis as AsyncRedis

from backend.core.runner_service import EventRunnerService


def get_runner_service(request: Request) -> EventRunnerService:
    return request.app.state.runner_service


def get_redis(request: Request) -> AsyncRedis:
    return request.app.state.redis
