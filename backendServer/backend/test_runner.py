from django.db import connections
from django.test.runner import DiscoverRunner

from events.models import BetterAuthAccount, BetterAuthUser


class NeonAuthTestRunner(DiscoverRunner):
    """The neon_auth.* tables are managed=False mirrors of the Better Auth
    (Next.js) schema, so Django's normal test-DB setup skips them. Build the
    `neon_auth` schema and the tables the suite inserts into (`user`, `account`)
    once, centrally, right after the standard test databases are created — so no
    individual test class has to repeat the schema_editor dance.
    """

    def setup_databases(self, **kwargs):
        config = super().setup_databases(**kwargs)
        # Fast-tier-only runs (plain unittest.TestCase) need no DB, so Django
        # builds none — don't reach for `default` and hit the real database.
        if 'default' not in kwargs.get('aliases', set()):
            return config
        connection = connections['default']
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA IF NOT EXISTS neon_auth')
        with connection.schema_editor() as editor:
            editor.create_model(BetterAuthUser)
            editor.create_model(BetterAuthAccount)
        return config
