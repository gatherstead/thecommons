import os
import sys
from urllib.parse import parse_qsl, urlparse

from .base import *  # noqa: F403  # Django settings override files use star imports by convention

DEBUG = True

# Tests run under dev settings — use an in-process cache so the suite doesn't
# need a running Redis (and stays isolated between test methods).
if "test" in sys.argv:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-in-prod")

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

_db_url = os.getenv("DATABASE_URL")
if not _db_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Point it at the Neon dev branch in backendServer/.env "
        "(see docs/dev-db-isolation.md)."
    )
_db = urlparse(_db_url)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.replace("/", ""),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": 5432,
        "OPTIONS": dict(parse_qsl(_db.query)),
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Optional: point at the prod Neon branch so the devtool sources dropdown
# can list prod sources.  Set PROD_DATABASE_URL in backendServer/.env.
_prod_db_url = os.getenv("PROD_DATABASE_URL")
if _prod_db_url:
    _pdb = urlparse(_prod_db_url)
    DATABASES["prod_readonly"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _pdb.path.replace("/", ""),
        "USER": _pdb.username,
        "PASSWORD": _pdb.password,
        "HOST": _pdb.hostname,
        "PORT": 5432,
        "OPTIONS": dict(parse_qsl(_pdb.query)),
    }

# No long-running worker in dev — spawn a one-shot worker on submit/retry so
# forms get processed without running the worker by hand. Override with
# BROADCAST_AUTOSPAWN_WORKER=false to use a manual `run_broadcast_worker`.
BROADCAST_AUTOSPAWN_WORKER = os.getenv("BROADCAST_AUTOSPAWN_WORKER", "true").lower() == "true"

INSTALLED_APPS = [*INSTALLED_APPS, "devtools.apps.DevtoolsConfig"]  # noqa: F405  # star import is intentional
