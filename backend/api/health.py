import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(db: AsyncSession = Depends(get_db)):
    # Verify DB connectivity
    await db.execute(text("SELECT 1"))

    # Verify Redis connectivity
    r = aioredis.from_url(settings.redis_url)
    await r.ping()
    await r.aclose()

    return {"status": "ok"}
