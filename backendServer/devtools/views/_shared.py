import ipaddress
import socket
from functools import wraps
from urllib.parse import urlparse

from django.conf import settings
from django.http import Http404

# ── SSRF guard ────────────────────────────────────────────────────────────────

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"}


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got '{parsed.scheme}'")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked hostname: {hostname}")

    try:
        resolved = socket.gethostbyname(hostname)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc

    ip = ipaddress.ip_address(resolved)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise ValueError(f"Resolved IP {resolved} is not a public address")


def _resolve_db(request):
    db = request.GET.get("db", "default")
    if db not in ("default", "prod_readonly") or db not in settings.DATABASES:
        db = "default"
    return db


def _debug_only(view_func):
    """Raise Http404 for every request unless settings.DEBUG is on.

    Replaces the identical inline `if not settings.DEBUG: raise Http404`
    guard that used to open each devtools view.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404
        return view_func(request, *args, **kwargs)

    return wrapper
