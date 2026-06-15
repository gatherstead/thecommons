import os
from urllib.parse import urlparse, parse_qsl
from .base import *

DEBUG = True

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
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _db.path.replace('/', ''),
        'USER': _db.username,
        'PASSWORD': _db.password,
        'HOST': _db.hostname,
        'PORT': 5432,
        'OPTIONS': dict(parse_qsl(_db.query)),
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# No long-running worker in dev — spawn a one-shot worker on submit/retry so
# forms get processed without running the worker by hand. Override with
# BROADCAST_AUTOSPAWN_WORKER=false to use a manual `run_broadcast_worker`.
BROADCAST_AUTOSPAWN_WORKER = os.getenv("BROADCAST_AUTOSPAWN_WORKER", "true").lower() == "true"
