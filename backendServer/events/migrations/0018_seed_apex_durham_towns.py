from django.db import migrations

# Coverage expansion beyond Chatham County. Gemini geocodes a recurring stream
# of host/scraper submissions (farm camps at Old Mill Farm, Sun Star Farm,
# Tinkering School, etc.) to Apex (Wake County) and Durham (Durham County) —
# venues just over the county line from the existing Chatham service area. Until
# now those slugs had no `Town` row, so `publish_all_approved` skipped them
# (`skipped_no_town`) and ~27 otherwise-ready events sat unpublished. Adding the
# two Towns brings them into coverage; `manage.py reopen_skipped_towns` flips any
# already-skipped rows back to `approved` for the next publish. "durham" is
# already a valid broadcast routing region (see broadcast/routing.py), so this
# aligns event coverage with the broadcast side.
TOWNS = [
    ("apex", "Apex"),
    ("durham", "Durham"),
]


def seed_towns(apps, schema_editor):
    Town = apps.get_model("events", "Town")
    for slug, name in TOWNS:
        Town.objects.get_or_create(slug=slug, defaults={"name": name})


def unseed_towns(apps, schema_editor):
    # Both towns are genuinely new here, so this is safely reversible. Events
    # point at Town with on_delete=SET_NULL, so removing the rows nulls their
    # town rather than cascading a delete.
    Town = apps.get_model("events", "Town")
    Town.objects.filter(slug__in=["apex", "durham"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0017_backfill_null_town_events"),
    ]

    operations = [
        migrations.RunPython(seed_towns, unseed_towns),
    ]
