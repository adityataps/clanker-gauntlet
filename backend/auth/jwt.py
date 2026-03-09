"""
JWT issue and verification using authlib.
Used when AUTH_PROVIDER=jwt (local dev / self-hosted deployments).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from authlib.jose import jwt, JoseError

from backend.config import settings

_HEADER = {"alg": settings.jwt_algorithm}


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Issue a signed JWT. `subject` is the user's UUID string."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        **(extra_claims or {}),
    }
    return jwt.encode(_HEADER, payload, settings.jwt_secret_key).decode()


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Validate and decode a JWT. Raises authlib.jose.JoseError on failure
    (expired, bad signature, malformed).
    """
    claims = jwt.decode(token, settings.jwt_secret_key)
    claims.validate()
    return dict(claims)
