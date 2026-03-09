"""
FastAPI dependency: get_current_user

Routes to JWT or Auth0 validation based on AUTH_PROVIDER setting.
Inject into any endpoint that requires an authenticated user:

    @router.get("/me")
    async def me(user: User = Depends(get_current_user)):
        ...
"""

import uuid
from typing import Annotated

from authlib.jose import JoseError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import User
from backend.db.session import get_db

_bearer = HTTPBearer()


async def _resolve_user_from_sub(sub: str, db: AsyncSession) -> User:
    """
    Look up a User by their subject claim (UUID for JWT, Auth0 sub for Auth0).
    Raises 401 if the user doesn't exist in the DB.
    """
    # JWT subs are UUIDs; Auth0 subs are strings like "auth0|abc123"
    stmt = (
        select(User).where(User.auth0_sub == sub)
        if "|" in sub
        else select(User).where(User.id == uuid.UUID(sub))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        if settings.auth_provider == "jwt":
            from backend.auth.jwt import decode_access_token

            claims = decode_access_token(token)
        else:
            from backend.auth.auth0 import decode_auth0_token

            claims = await decode_auth0_token(token)
    except (JoseError, ValueError):
        raise credentials_exception from None

    sub = claims.get("sub")
    if not sub:
        raise credentials_exception

    return await _resolve_user_from_sub(sub, db)
