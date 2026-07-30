"""Backfill `town` for the 15 live events (ticket 36.2) that shipped with
`town = NULL`.

All 15 rows have an empty `source_name`, which points at hand-entered events
that predate the ingestion pipeline, not at a pipeline classification miss.

## Was 0004 the cause?

Ticket 36.2 hypothesised that `0004_add_town_model.migrate_town_strings_to_fk`
(which only assigned a `Town` FK when the old `town_str` matched an
already-seeded slug, and 0004 seeded only `carrboro`/`pittsboro`) is why these
rows are NULL. Reading 0004 confirms the mechanism is real — any `town_str`
outside `{carrboro, pittsboro}` would silently become NULL FK — but it does
not explain *these* 15 rows specifically: 0004 ran once, at migration time,
against whatever events existed then. These 15 rows carry an empty
`source_name`, meaning they were entered by hand (through the site's own
create-event flow or admin), not carried over from a pre-Town-model
`town_str`. The 0004 code path is a real bug class (confirmed by reading the
code), but it is not the origin of this particular batch — the more likely
explanation is that these were hand-created with no `town` selected, or with
a value that didn't resolve to an existing `Town`.

## Venue -> town mapping (see ticket for full source list)

- "Fair Game Beverage Company" -> pittsboro (192 Lorax Lane, Pittsboro, NC;
  Chatham Beverage District, on the eastern edge of Pittsboro).
- "bmc brewing" -> pittsboro (213 Lorax Ln, Pittsboro, NC; same Beverage
  District complex as Fair Game).
- "Chatham YMCA" -> pittsboro (120 Parkland Drive, Pittsboro, NC; branded
  "Chatham Park YMCA").
- "Covenant Place" (11 rows, the recurring "Senior ..." series) -> carrboro.
  The building's postal address is 103 Culbreth Rd, Chapel Hill, NC 27516,
  but the events themselves are Carrboro Parks & Recreation programming,
  calendared directly on the Town of Carrboro's own site
  (townofcarrboro.org/Calendar.aspx, carrbororec.org) — i.e. Carrboro Rec runs
  this senior series at Covenant Place. That is the operative "town" for a
  reader browsing what's on in Carrboro, so carrboro (not chapel-hill, which
  is also a covered Town slug) is the unambiguous choice here.
- "Jordan Lake State Recreation Area – Ne..." (the spring cleanup) -> left
  NULL. Jordan Lake State Recreation Area spans Wake and Chatham counties
  with access points on both the eastern shore (near Apex) and western shore
  (near Pittsboro/New Hope). No single covered Town slug is correct for the
  park as a whole, and the specific access point for this cleanup isn't
  resolvable from the data on hand. A wrong town would misplace this event on
  the wrong hub page, so it stays NULL per ticket guidance.

Reversible: `unbackfill` restores every row this migration touches to NULL
(scoped by uuid, not by venue/town, so it can't clobber unrelated events).
"""
from django.db import migrations

# (venue, town_slug) for every row this migration assigns a town to.
VENUE_TOWN_MAP = {
    "Fair Game Beverage Company": "pittsboro",
    "bmc brewing": "pittsboro",
    "Chatham YMCA": "pittsboro",
    "Covenant Place": "carrboro",
}

# Venues intentionally left NULL, and why — for anyone auditing later.
LEFT_NULL = {
    "Jordan Lake State Recreation Area – New Hope Overlook Access": (
        "Spans Wake/Chatham counties with access points in multiple towns; "
        "no single covered Town slug is correct."
    ),
}


def backfill_towns(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Town = apps.get_model("events", "Town")

    for venue, slug in VENUE_TOWN_MAP.items():
        town = Town.objects.filter(slug=slug).first()
        if town is None:
            # Covered-town list has drifted; don't guess, don't crash the migration.
            continue
        Event.objects.filter(venue=venue, town__isnull=True, source_name="").update(town=town)


def unbackfill_towns(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    for venue in VENUE_TOWN_MAP:
        Event.objects.filter(venue=venue, source_name="").update(town=None)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0016_seed_chatham_towns"),
    ]

    operations = [
        migrations.RunPython(backfill_towns, unbackfill_towns),
    ]
