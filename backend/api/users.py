import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.db.models import User
from backend.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])


class UserSearchResult(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
    q: Annotated[str, Query(min_length=2)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    pattern = f"%{q}%"
    result = await db.execute(
        select(User)
        .where(
            User.id != current_user.id,
            or_(User.email.ilike(pattern), User.display_name.ilike(pattern)),
        )
        .limit(20)
    )
    users = result.scalars().all()
    return [UserSearchResult(id=u.id, email=u.email, display_name=u.display_name) for u in users]
