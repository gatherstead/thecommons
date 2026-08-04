import os
from urllib.parse import parse_qsl, urlparse

from .base import *  # noqa: F403  # Django settings override files use star imports by convention

DEBUG = False

# nginx proxies to gunicorn over a Unix socket, which leaves REMOTE_ADDR empty —
# django-ratelimit's default key="ip" reads REMOTE_ADDR directly and raises
# ImproperlyConfigured (-> 500) when it's blank. Point it at the header nginx
# sets instead (proxy_set_header X-Real-IP $remote_addr;).
RATELIMIT_IP_META_KEY = "HTTP_X_REAL_IP"

# nginx terminates TLS and proxies to gunicorn over a Unix socket, so Django never
# sees an HTTPS connection directly — request.is_secure() (and anything built on it,
# like build_absolute_uri()) would compute False for every request, producing
# http:// URLs on an https:// site. Trust the header nginx always sets instead
# (proxy_set_header X-Forwarded-Proto $scheme; on every server block).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # crash at startup if missing

ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")

_db = urlparse(os.environ["DATABASE_URL"])
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.replace("/", ""),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": 5432,
        "OPTIONS": dict(parse_qsl(_db.query)),
        # Deliberately not pooling: 0 means Django closes the connection after each
        # request, so idle Django holds no open connection and Neon compute can autosuspend.
        "CONN_MAX_AGE": 0,
    }
}
