import uuid

from django.db import migrations, models


# Adds an unguessable manage_token per NewsletterSubscriber so prefs can be
# managed via a login-free URL (38.B1). A plain AddField with a callable
# default evaluates uuid.uuid4() once and writes the *same* value to every
# existing row, which would violate unique=True on a non-empty table. So the
# field lands first without the uniqueness constraint, gets a distinct value
# backfilled per row, and only then has unique=True enforced.
def backfill_manage_tokens(apps, schema_editor):
    NewsletterSubscriber = apps.get_model("events", "NewsletterSubscriber")
    for subscriber in NewsletterSubscriber.objects.all():
        subscriber.manage_token = uuid.uuid4()
        subscriber.save(update_fields=["manage_token"])


def noop_reverse(apps, schema_editor):
    # Tokens are opaque and only meaningful going forward; nothing to restore.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0018_seed_apex_durham_towns"),
    ]

    operations = [
        migrations.AddField(
            model_name="newslettersubscriber",
            name="manage_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=False, db_index=False),
        ),
        migrations.RunPython(backfill_manage_tokens, noop_reverse),
        migrations.AlterField(
            model_name="newslettersubscriber",
            name="manage_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True),
        ),
    ]
