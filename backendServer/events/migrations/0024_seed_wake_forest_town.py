from django.db import migrations

# Verified against the local dev Neon branch: no "wake-forest" row yet.
TOWNS = [
    ("wake-forest", "Wake Forest"),
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
        ("events", "0023_seed_raleigh_cary_morrisville_towns"),
    ]

    operations = [
        migrations.RunPython(seed_towns, unseed_towns),
    ]
