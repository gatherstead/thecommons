from datetime import UTC, datetime

from django.test import TestCase, tag

from events.models import Event, Town
from ingestion.deduplicator import find_duplicate
from ingestion.models import StagedEvent
from ingestion.services import publish_all_approved

START = datetime(2099, 6, 1, 18, 0, tzinfo=UTC)


@tag("db")
class PublishAllApprovedTests(TestCase):
    def setUp(self):
        Town.objects.get_or_create(slug="carrboro", defaults={"name": "Carrboro"})

    def _staged(self, title, status, town="Carrboro", **kwargs):
        return StagedEvent.objects.create(
            title=title,
            description="d",
            location_name="Venue",
            town=town,
            start_datetime=START,
            status=status,
            **kwargs,
        )

    def test_only_approved_events_are_published(self):
        """publish_all_approved no longer deletes the rows it sweeps — it flips
        them to a terminal status="published" and leaves them in place. They
        are the deduplicator's matching corpus (CANDIDATE_STATUSES includes
        "published"), and duplicate_of is on_delete=SET_NULL, so deleting a
        published anchor would silently orphan any row still pointing at it.
        `removed` therefore no longer means "deleted" — it means "swept out of
        the approved queue" (approved -> published), and the row count is
        unchanged by a publish sweep.
        """
        self._staged("Approved Show", "approved")
        self._staged("Pending Show", "pending")
        self._staged("Rejected Show", "rejected")
        self._staged("Duplicate Show", "duplicate")

        result = publish_all_approved()

        self.assertEqual(result["published"], 1)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(list(Event.objects.values_list("title", flat=True)), ["Approved Show"])
        # The published staged row survives with a terminal status; the
        # others remain untouched.
        published_row = StagedEvent.objects.get(title="Approved Show")
        self.assertEqual(published_row.status, "published")
        self.assertEqual(StagedEvent.objects.count(), 4)

    def test_no_approved_events_is_noop(self):
        self._staged("Pending Show", "pending")
        result = publish_all_approved()
        self.assertEqual(result, {"published": 0, "already_published": 0, "removed": 0})
        self.assertFalse(Event.objects.exists())

    def test_published_row_still_found_as_dedupe_candidate(self):
        """A published row is a permanent dedupe anchor: a later re-scrape or
        re-submission of the same event must still match against it, even
        though it's no longer "approved".
        """
        self._staged("Approved Show", "approved")
        publish_all_approved()
        published_row = StagedEvent.objects.get(title="Approved Show")
        self.assertEqual(published_row.status, "published")

        # find_duplicate only matches against rows with a lower pk (see its
        # docstring), so the candidate must be a saved, later row.
        candidate = self._staged("Approved Show", "pending")
        dup = find_duplicate(candidate)
        self.assertEqual(dup, published_row)

    def test_duplicate_of_pointers_survive_publish_sweep(self):
        """duplicate_of is on_delete=SET_NULL — if publish_all_approved still
        deleted the approved row, a duplicate row pointing at it would silently
        lose that pointer. Since the row now survives (as status="published"),
        the pointer must survive too.
        """
        original = self._staged("Approved Show", "approved")
        dupe = self._staged("Approved Show (dupe)", "duplicate", duplicate_of=original)

        publish_all_approved()

        dupe.refresh_from_db()
        original.refresh_from_db()
        self.assertEqual(original.status, "published")
        self.assertEqual(dupe.duplicate_of_id, original.id)

    def test_chatham_county_towns_publish(self):
        """Regression for 35.14. Gemini classifies Chatham County events into
        "Siler City" / "Bynum"; before events 0016 seeded those Towns, every one
        of them hit the `no Town matches slug` branch and was skipped — ~26 in a
        single prod run, including an event titled "Chatham County Parks and
        Recreation Summer Camp". Pittsboro, the county seat, was already covered.
        """
        self._staged("Growers & Makers Market", "approved", town="Siler City")
        self._staged("Bynum Front Porch Music", "approved", town="Bynum")

        result = publish_all_approved()

        self.assertEqual(result["published"], 2)
        self.assertEqual(
            dict(Event.objects.values_list("title", "town__slug")),
            {"Growers & Makers Market": "siler-city", "Bynum Front Porch Music": "bynum"},
        )

    def test_unmatched_town_is_skipped_but_retried(self):
        """A town outside coverage (Apex is not in the service area) is still
        skipped — but the row keeps published_event=None, so the terminal
        approved->published sweep leaves it alone and the next run retries it.
        That is why adding a Town row backfills previously-dropped events with
        no separate migration.
        """
        self._staged("Somewhere Else", "approved", town="Apex")

        result = publish_all_approved()

        self.assertEqual(result["published"], 0)
        self.assertEqual(result["removed"], 0)
        self.assertFalse(Event.objects.exists())
        self.assertEqual(StagedEvent.objects.get(title="Somewhere Else").status, "approved")
