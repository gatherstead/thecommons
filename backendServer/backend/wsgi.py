"""
WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Must be set before Django initialises (import below triggers settings load).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402,I001  # load_dotenv() + env must run first

application = get_wsgi_application()
