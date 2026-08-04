"""Suite 47.3 — delete retired Tag rows outright.

`lgbtq-friendly` and `speaks-spanish` were retired from the product, and
`weekends-only`/`evenings-only`/`daytime-only` are the pre-canonicalization
day-part slugs (superseded by `weekends`/`evenings`/`daytime`, now computed
from `Event.date` — see events/tagging.py). Deleting the Tag rows cascades
the M2M through-table rows, so any event still linked to one just loses that
tag; its other tags are untouched.

Run order in prod: run `manage.py retag_events` BEFORE this migration. That
command already strips these legacy day-part slugs off every event and
replaces them with the computed tag, so by the time this migration runs the
`-only` rows are typically already orphaned (0 event links). Running this
migration first wouldn't break retag_events — it recomputes tags from
event.date regardless of which Tag rows currently exist — but retag_events'
own "legacy slugs collapsed" count would then read 0 instead of the real
number, since the rows it's looking for would already be gone.

Not reversible: `reverse_code` is a no-op. The Tag names could be recreated,
but the event/tag links this migration deletes cannot be reconstructed —
pretending this is reversible would be misleading.
"""

from django.db import migrations

RETIRED_TAG_NAMES = [
    "lgbtq-friendly",
    "speaks-spanish",
    "weekends-only",
    "evenings-only",
    "daytime-only",
]


def delete_retired_tags(apps, schema_editor):
    Tag = apps.get_model("events", "Tag")
    Tag.objects.filter(name__in=RETIRED_TAG_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0024_seed_wake_forest_town"),
    ]

    operations = [
        migrations.RunPython(delete_retired_tags, migrations.RunPython.noop),
    ]
