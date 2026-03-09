"""
Auth0 token validation.
Used when AUTH_PROVIDER=auth0 (hosted / production deployments).

Fetches the Auth0 JWKS on first use and caches it for the process lifetime.
Tokens are RS256-signed JWTs issued by Auth0.
"""

import httpx
from authlib.jose import jwt, JoseError, JsonWebKey

from backend.config import settings

_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def decode_auth0_token(token: str) -> dict:
    """
    Validate an Auth0 JWT against the tenant's JWKS.
    Raises authlib.jose.JoseError on invalid/expired tokens.
    Raises ValueError if audience claim doesn't match.
    """
    jwks = await _get_jwks()
    key_set = JsonWebKey.import_key_set(jwks)
    claims = jwt.decode(token, key_set)
    claims.validate()

    if settings.auth0_audience and claims.get("aud") != settings.auth0_audience:
        # aud can be a list
        aud = claims.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]
        if settings.auth0_audience not in aud:
            raise ValueError("Token audience does not match expected audience")

    return dict(claims)
