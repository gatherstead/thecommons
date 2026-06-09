import os
from urllib.parse import urlparse, parse_qsl
from .base import *

DEBUG = True

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-in-prod")

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

_db = urlparse(os.getenv("DATABASE_URL", ""))
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
