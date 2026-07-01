"""Regression coverage for the Unix-socket REMOTE_ADDR gap: nginx proxies to
gunicorn over a Unix socket in prod, which leaves REMOTE_ADDR empty.
django-ratelimit's key="ip" reads REMOTE_ADDR directly and raised
ImproperlyConfigured (-> unhandled 500) before prod.py pointed
RATELIMIT_IP_META_KEY at the X-Real-IP header nginx sets instead.

Two tests mirror the two topologies this app actually runs under:
- dev/test (base.py/dev.py): no RATELIMIT_IP_META_KEY override, REMOTE_ADDR is
  populated directly by runserver/the test Client.
- prod (prod.py): RATELIMIT_IP_META_KEY = "HTTP_X_REAL_IP", REMOTE_ADDR empty.

Neither test uses @override_settings(RATELIMIT_ENABLE=False) -- that would
disable the exact code path that crashed.
"""
from django.test import SimpleTestCase, override_settings, tag
from rest_framework.test import APIClient


@tag("fast")
class DevTopologyRateLimitTest(SimpleTestCase):
    """Dev/test settings: REMOTE_ADDR is populated directly, no proxy header needed."""

    def test_direct_recipe_rate_limits_by_remote_addr(self):
        client = APIClient()
        resp = client.post(
            "/broadcast/direct-recipe",
            {"site_key": "does-not-matter", "event": {}},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertNotEqual(resp.status_code, 500)


@tag("fast")
@override_settings(RATELIMIT_IP_META_KEY="HTTP_X_REAL_IP")
class ProdTopologyRateLimitTest(SimpleTestCase):
    """Prod settings (prod.py): nginx proxies over a Unix socket, so REMOTE_ADDR
    is empty and nginx sets X-Real-IP instead (proxy_set_header X-Real-IP
    $remote_addr;). Simulated here via @override_settings + an empty REMOTE_ADDR,
    since the test suite otherwise runs under dev/test settings.
    """

    def test_direct_recipe_rate_limits_by_x_real_ip_with_empty_remote_addr(self):
        client = APIClient()
        resp = client.post(
            "/broadcast/direct-recipe",
            {"site_key": "does-not-matter", "event": {}},
            format="json",
            REMOTE_ADDR="",
            HTTP_X_REAL_IP="203.0.113.5",
        )
        self.assertNotEqual(resp.status_code, 500)
