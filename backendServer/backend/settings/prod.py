import os
from urllib.parse import urlparse, parse_qsl
from .base import *

DEBUG = False

# nginx proxies to gunicorn over a Unix socket, which leaves REMOTE_ADDR empty —
# django-ratelimit's default key="ip" reads REMOTE_ADDR directly and raises
# ImproperlyConfigured (-> 500) when it's blank. Point it at the header nginx
# sets instead (proxy_set_header X-Real-IP $remote_addr;).
RATELIMIT_IP_META_KEY = "HTTP_X_REAL_IP"

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # crash at startup if missing

ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")

_db = urlparse(os.environ["DATABASE_URL"])
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
