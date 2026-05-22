from django.db import migrations


class Migration(migrations.Migration):
    """
    Cast the two remaining TEXT FK columns that reference neon_auth.user.id
    (now UUID after migration 0010) to UUID, so ORM queries like
    filter(created_by=user) / filter(submitted_by=user) stop failing with
    'operator does not exist: text = uuid'.

    Each column also has a text_pattern_ops LIKE index from when it was TEXT;
    those must be dropped before the cast and are not recreated (UUID columns
    need only the plain btree index that Django leaves in place).
    """

    dependencies = [
        ("events", "0010_fix_userprofile_user_id_type"),
        ("ingestion", "0005_stagedevent_submitted_by"),
    ]

    operations = [
        # ── events_event.created_by_id ─────────────────────────────────────
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS events_event_created_by_id_2c28ea90_like;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="ALTER TABLE events_event ALTER COLUMN created_by_id TYPE uuid USING created_by_id::uuid;",
            reverse_sql="ALTER TABLE events_event ALTER COLUMN created_by_id TYPE text USING created_by_id::text;",
        ),

        # ── ingestion_stagedevent.submitted_by_id ──────────────────────────
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS ingestion_stagedevent_submitted_by_id_e71b4535_like;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ingestion_stagedevent ALTER COLUMN submitted_by_id TYPE uuid USING submitted_by_id::uuid;",
            reverse_sql="ALTER TABLE ingestion_stagedevent ALTER COLUMN submitted_by_id TYPE text USING submitted_by_id::text;",
        ),
    ]
