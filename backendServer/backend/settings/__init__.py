"""Settings dispatch — `DJANGO_ENV` selects the active settings module.

`prod` -> prod.py, `dev` (and unset, for local DX) -> dev.py. A *set but
unrecognized* value is a hard error, not a silent fallback.

Why the hard error: the June 2026 "no events" outage was `DJANGO_ENV` simply
missing in prod, so the app silently served dev.py — whose localhost-only
ALLOWED_HOSTS rejected api.thecommons.town with DisallowedHost (HTTP 400). The
unset case still defaults to dev (every laptop relies on that), but a typo like
`DJANGO_ENV=production` now fails loud. The deploy health check
(`manage.py healthcheck --require-prod`) catches the remaining unset-in-prod case.
"""
import os

from django.core.exceptions import ImproperlyConfigured

VALID_ENVS = ("dev", "prod")


def select_settings_env(environ=None) -> str:
    """Resolve the settings env name ('dev' | 'prod') from DJANGO_ENV.

    Unset/empty -> 'dev'. A set-but-unrecognized value raises
    ImproperlyConfigured rather than silently falling back to dev.
    """
    if environ is None:
        environ = os.environ
    raw = environ.get("DJANGO_ENV")
    if not raw or not raw.strip():
        return "dev"
    env = raw.strip().lower()
    if env not in VALID_ENVS:
        raise ImproperlyConfigured(
            f"DJANGO_ENV={raw!r} is not a recognized environment; "
            f"expected one of {VALID_ENVS} (or unset for dev)."
        )
    return env


if select_settings_env() == "prod":
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
