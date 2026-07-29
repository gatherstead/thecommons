from django.db import migrations


# Chatham County coverage. Pittsboro (the county seat) was already covered by
# 0004, but Siler City and Bynum were not — so Gemini classified their events
# into slugs with no `Town` row and `publish_approved_events` dropped them.
# `chapel-hill` is listed because it exists in prod but was never seeded by a
# migration; including it here makes a fresh database match prod.
TOWNS = [
    ("chapel-hill", "Chapel Hill"),
    ("siler-city", "Siler City"),
    ("bynum", "Bynum"),
]


def seed_towns(apps, schema_editor):
    Town = apps.get_model("events", "Town")
    for slug, name in TOWNS:
        Town.objects.get_or_create(slug=slug, defaults={"name": name})


def unseed_towns(apps, schema_editor):
    # Only the two genuinely new towns are reversible. `chapel-hill` predates
    # this migration in prod, so removing it on rollback would be destructive.
    # Events point at Town with on_delete=SET_NULL, so this is non-cascading.
    Town = apps.get_model("events", "Town")
    Town.objects.filter(slug__in=["siler-city", "bynum"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0015_seed_digest_beat"),
    ]

    operations = [
        migrations.RunPython(seed_towns, unseed_towns),
    ]
