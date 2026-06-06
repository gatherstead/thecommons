import time
from typing import Any

import jwt
import requests
from django.conf import settings
from jwt import PyJWKClient

_JWKS_TTL_SECONDS = 600
_JWKS_STALE_GRACE_SECONDS = 3600

_jwks_cache: dict[str, Any] = {
    "client": None,
    "fetched_at": 0.0,
    "stale_after": 0.0,
}


def _get_jwks_client() -> PyJWKClient | None:
    """Return a PyJWKClient, refreshing in-process at TTL.

    On fetch failure inside the stale-grace window, the previous client is
    reused so a Next.js outage doesn't cascade into Django auth.
    """
    now = time.monotonic()
    cached = _jwks_cache["client"]

    if cached is not None and now < _jwks_cache["fetched_at"] + _JWKS_TTL_SECONDS:
        return cached

    jwks_url = getattr(settings, "BETTER_AUTH_JWKS_URL", "")
    if not jwks_url:
        return cached

    try:
        requests.get(jwks_url, timeout=3).raise_for_status()
        client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=_JWKS_TTL_SECONDS)
        _jwks_cache["client"] = client
        _jwks_cache["fetched_at"] = now
        _jwks_cache["stale_after"] = now + _JWKS_TTL_SECONDS + _JWKS_STALE_GRACE_SECONDS
        return client
    except Exception:
        if cached is not None and now < _jwks_cache["stale_after"]:
            return cached
        return None


def verify_better_auth_jwt(token: str) -> dict | None:
    client = _get_jwks_client()
    if client is None:
        return None

    issuer = getattr(settings, "BETTER_AUTH_ISSUER", "") or None
    audience = getattr(settings, "BETTER_AUTH_AUDIENCE", "") or None

    try:
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "RS256", "ES256"],
            issuer=issuer,
            audience=audience,
            options={"verify_aud": bool(audience)},
        )
    except jwt.PyJWTError:
        return None
