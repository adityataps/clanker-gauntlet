from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis

from backend.db.session import get_db
from backend.config import settings

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
