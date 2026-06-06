import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0009_add_newsletter_subscriber"),
    ]

    operations = [
        # Update Django's migration state to match the actual UUID type that
        # Better Auth uses for neon_auth.user.id. The managed=False model means
        # no DDL is emitted for the neon_auth table itself.
        migrations.AlterField(
            model_name="betterauthuser",
            name="id",
            field=models.UUIDField(primary_key=True, serialize=False),
        ),
        # Drop the text_pattern_ops LIKE index Django added for the TextField.
        # It cannot survive the cast to uuid (uuid doesn't support that operator
        # class) and is not needed — UUID columns are queried by equality only.
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS events_userprofile_user_id_2fd91d02_like;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Cast the FK column in the managed table to match.
        # USING user_id::uuid converts the existing TEXT values in-place;
        # all values are valid UUID strings written by Better Auth.
        migrations.RunSQL(
            sql="ALTER TABLE events_userprofile ALTER COLUMN user_id TYPE uuid USING user_id::uuid;",
            reverse_sql="ALTER TABLE events_userprofile ALTER COLUMN user_id TYPE text USING user_id::text;",
        ),
    ]
