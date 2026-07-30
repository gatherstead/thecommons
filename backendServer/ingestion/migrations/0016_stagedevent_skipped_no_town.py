from django.db import migrations, models


# Backfill for ticket 36.1: prod has 27 StagedEvent rows stuck `approved` with
# `published_event=None` — towns deliberately out of coverage (Apex 15, Durham
# 12) that `publish_all_approved` re-logs and re-skips on every single pipeline
# run. Converting them to the new terminal-ish `skipped_no_town` status here
# (rather than waiting for the next publish run) means the very first run after
# this migration deploys is already quiet, instead of logging one more round.
def backfill_skipped_no_town(apps, schema_editor):
    StagedEvent = apps.get_model("ingestion", "StagedEvent")
    Town = apps.get_model("events", "Town")

    known_slugs = set(Town.objects.values_list("slug", flat=True))
    stuck = StagedEvent.objects.filter(status="approved", published_event__isnull=True)

    to_update = []
    for staged in stuck:
        town_slug = staged.town.lower().replace(" ", "-") if staged.town else None
        if town_slug not in known_slugs:
            staged.status = "skipped_no_town"
            to_update.append(staged)

    if to_update:
        StagedEvent.objects.bulk_update(to_update, ["status"])


def unbackfill_skipped_no_town(apps, schema_editor):
    # Reversible but coarse: every `skipped_no_town` row reverts to `approved`,
    # matching the pre-migration state regardless of which run produced it.
    StagedEvent = apps.get_model("ingestion", "StagedEvent")
    StagedEvent.objects.filter(status="skipped_no_town").update(status="approved")


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0016_seed_chatham_towns"),
        ("ingestion", "0015_alter_stagedevent_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stagedevent",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("duplicate", "Duplicate"),
                    ("published", "Published"),
                    ("skipped_no_town", "Skipped — No Matching Town"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_skipped_no_town, unbackfill_skipped_no_town),
    ]
