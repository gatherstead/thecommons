import os

from .dev import *

# Inherits dev.py's DATABASE_URL -> Postgres parsing. Django auto-creates a
# throwaway test_<dbname> on that server, so the suite never touches dev data.
# Postgres is a locked decision — do NOT switch this to SQLite.

# Neon's pooler (PgBouncer) endpoint can't CREATE/DROP a test database — the
# drop fails at teardown with "database is being accessed by other users". The
# direct endpoint is the pooler host minus the "-pooler" suffix; rewrite to it
# so the throwaway test_<dbname> can be created and dropped cleanly.
DATABASES['default']['HOST'] = DATABASES['default']['HOST'].replace('-pooler', '')

# Central neon_auth handling: the managed=False BetterAuth mirrors aren't built
# by the normal test-DB setup, so a custom runner creates the schema + table.
TEST_RUNNER = 'backend.test_runner.NeonAuthTestRunner'

# Celery runs inline — no Redis/worker needed, and failures propagate.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Local-memory cache unconditionally (dev.py only swaps it when 'test' in argv).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Fast, insecure hashing — fine for tests, ~no cost per created user.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Stub external-service credentials so nothing reaches the network.
GEMINI_API_KEY = 'test'
BETTER_AUTH_JWKS_URL = 'http://test/jwks'
CRON_SECRET = 'test'
THE_COMMONS_API_KEY = 'test'

# These two are read from os.environ directly (not via settings), so stub the
# env: BREVO in events/email_service.py, access codes in broadcast/access.py.
os.environ['BREVO_API_KEY'] = 'test'
os.environ['BROADCAST_ACCESS_CODES'] = 'test:testcode'
