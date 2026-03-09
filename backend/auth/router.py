"""
Auth endpoints.

JWT mode  (AUTH_PROVIDER=jwt):
  POST /auth/register   create account + return token
  POST /auth/login      verify password + return token
  GET  /auth/me         return current user profile

Auth0 mode (AUTH_PROVIDER=auth0):
  GET  /auth/login      redirect to Auth0 Universal Login
  GET  /auth/callback   handle Auth0 callback, upsert user, return token
  GET  /auth/me         return current user profile

Both modes share /auth/me and the User upsert logic.
"""

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.config import settings
from backend.db.models import User
from backend.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Pydantic schemas (request / response)
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    has_anthropic_key: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# JWT endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if settings.auth_provider != "jwt":
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=_pwd_context.hash(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    from backend.auth.jwt import create_access_token
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if settings.auth_provider != "jwt":
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not _pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    from backend.auth.jwt import create_access_token
    return TokenResponse(access_token=create_access_token(str(user.id)))


# ---------------------------------------------------------------------------
# Auth0 endpoints
# ---------------------------------------------------------------------------

@router.get("/login")
async def auth0_login(request: Request):
    if settings.auth_provider != "auth0":
        raise HTTPException(status_code=404, detail="Not found")

    from authlib.integrations.starlette_client import OAuth
    oauth = OAuth()
    oauth.register(
        name="auth0",
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        server_metadata_url=f"https://{settings.auth0_domain}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    redirect_uri = str(request.url_for("auth0_callback"))
    return await oauth.auth0.authorize_redirect(request, redirect_uri, audience=settings.auth0_audience)


@router.get("/callback", name="auth0_callback")
async def auth0_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if settings.auth_provider != "auth0":
        raise HTTPException(status_code=404, detail="Not found")

    from authlib.integrations.starlette_client import OAuth
    oauth = OAuth()
    oauth.register(
        name="auth0",
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        server_metadata_url=f"https://{settings.auth0_domain}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    token_data = await oauth.auth0.authorize_access_token(request)
    userinfo = token_data.get("userinfo", {})

    auth0_sub = userinfo.get("sub")
    email = userinfo.get("email", "")
    display_name = userinfo.get("name") or userinfo.get("nickname") or email.split("@")[0]

    # Upsert user
    result = await db.execute(select(User).where(User.auth0_sub == auth0_sub))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(auth0_sub=auth0_sub, email=email, display_name=display_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Issue our own JWT so the frontend uses the same token shape regardless of provider
    from backend.auth.jwt import create_access_token
    access_token = create_access_token(auth0_sub, extra_claims={"email": email})

    # Redirect to frontend with token in query param (frontend stores it)
    frontend_url = f"http://localhost:5173/auth/callback?token={access_token}"
    return RedirectResponse(url=frontend_url)


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        has_anthropic_key=current_user.anthropic_api_key_enc is not None,
    )
