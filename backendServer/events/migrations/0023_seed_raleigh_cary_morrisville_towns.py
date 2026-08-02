from django.db import migrations

# Verified against both the local dev Neon branch and prod_readonly: neither
# has these three yet. "raleigh" and "cary" are already valid broadcast
# routing localities (broadcast/routing.py), but that vocabulary is
# deliberately isolated from events.Town, so this is the first Town row for
# all three.
TOWNS = [
    ("raleigh", "Raleigh"),
    ("cary", "Cary"),
    ("morrisville", "Morrisville"),
]


def seed_towns(apps, schema_editor):
    Town = apps.get_model("events", "Town")
    for slug, name in TOWNS:
        Town.objects.get_or_create(slug=slug, defaults={"name": name})


def unseed_towns(apps, schema_editor):
    Town = apps.get_model("events", "Town")
    Town.objects.filter(slug__in=[slug for slug, _ in TOWNS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0022_move_newsletter_to_newsletter"),
    ]

    operations = [
        migrations.RunPython(seed_towns, unseed_towns),
    ]
