import json
from datetime import UTC, datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, tag

from events.models import Event, Town
from events.tests.factories import make_town, make_user
from ingestion.deduplicator import find_duplicate
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.services import ingest_direct_submission, publish_all_approved, resolve_town

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

    def test_unmatched_town_is_marked_skipped_no_town(self):
        """A town outside coverage (Greensboro is not in the service area) is
        moved to the terminal-ish `skipped_no_town` status rather than left
        `approved`. `approved` means "will be published", which was false for
        these rows — ticket 36.1. The row is not deleted (it survives as a
        dedupe anchor — see CANDIDATE_STATUSES) and no Event is created.
        """
        self._staged("Somewhere Else", "approved", town="Greensboro")

        result = publish_all_approved()

        self.assertEqual(result["published"], 0)
        self.assertEqual(result["removed"], 0)
        self.assertFalse(Event.objects.exists())
        self.assertEqual(StagedEvent.objects.get(title="Somewhere Else").status, "skipped_no_town")

    def test_force_town_is_a_fallback_not_an_override(self):
        """devtools' "force town" selector (e.g. the playground pinning a
        source to "Raleigh") must not flatten an event Gemini correctly
        placed in a different, covered town (e.g. "Cary") -- only a guess
        that doesn't resolve to a known Town should fall back to it.
        """
        cary = make_town(slug="cary", name="Cary")
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self._staged("Cary Show", "approved", town="Cary")

        publish_all_approved(force_town=raleigh)

        event = Event.objects.get(title="Cary Show")
        self.assertEqual(event.town_id, cary.id)

    def test_force_town_backfills_when_gemini_guess_is_empty(self):
        """The empty-string case is the one `force_town` exists for -- the
        standardizer prompt tells Gemini to return "" when it can't determine
        a town at all.
        """
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self._staged("Mystery Venue Show", "approved", town="")

        publish_all_approved(force_town=raleigh)

        event = Event.objects.get(title="Mystery Venue Show")
        self.assertEqual(event.town_id, raleigh.id)

    def test_force_town_backfills_when_gemini_guess_is_out_of_coverage(self):
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self._staged("Somewhere Else Forced", "approved", town="Greensboro")

        publish_all_approved(force_town=raleigh)

        event = Event.objects.get(title="Somewhere Else Forced")
        self.assertEqual(event.town_id, raleigh.id)

    def _staged_from_source(self, title, town, default_town=None, source_uid=None):
        """A staged event linked to a real RawEvent/EventSource pair, needed
        to exercise `EventSource.default_town` -- `_staged` alone leaves
        `raw_event` unset, which resolve_town's per-source fallback needs.
        """
        source = EventSource.objects.create(
            name=f"Source for {title}",
            source_type="ics",
            url=f"https://feed.test/{source_uid or title}.ics",
            default_town=default_town,
        )
        raw = RawEvent.objects.create(
            source=source,
            raw_title=title,
            raw_description="d",
            raw_start_datetime=START,
            source_uid=source_uid or title,
        )
        return self._staged(title, "approved", town=town, raw_event=raw)

    def test_default_town_backfills_when_gemini_guess_is_empty(self):
        """45.4: `EventSource.default_town` is the same fallback-not-override
        contract as devtools' `force_town`, just resolved per staged event
        inside the publish loop (each event's own source) instead of
        threaded down from the caller -- see `resolve_town`'s docstring.
        """
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self._staged_from_source("Mystery Venue Show", town="", default_town=raleigh)

        publish_all_approved()

        event = Event.objects.get(title="Mystery Venue Show")
        self.assertEqual(event.town_id, raleigh.id)

    def test_default_town_is_a_fallback_not_an_override(self):
        """Regression for the bug PR #42 already fixed once: a source's
        default_town must not flatten an event Gemini correctly placed in a
        different, covered town.
        """
        cary = make_town(slug="cary", name="Cary")
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self._staged_from_source("Cary Show", town="Cary", default_town=raleigh)

        publish_all_approved()

        event = Event.objects.get(title="Cary Show")
        self.assertEqual(event.town_id, cary.id)

    def test_no_default_town_behaves_as_today(self):
        """A source with no `default_town` set (the status quo) still lands a
        blank-town event in `skipped_no_town`, exactly as before 45.4.
        """
        self._staged_from_source("No Town Show", town="", default_town=None)

        result = publish_all_approved()

        self.assertEqual(result["published"], 0)
        self.assertFalse(Event.objects.exists())
        self.assertEqual(StagedEvent.objects.get(title="No Town Show").status, "skipped_no_town")

    def test_explicit_force_town_wins_over_source_default_town(self):
        """An operator's explicit `force_town` (devtools) still takes
        priority over a source's own `default_town` when both would apply --
        it's a more specific, deliberate choice for *this run*.
        """
        source_default = make_town(slug="raleigh", name="Raleigh")
        operator_choice = make_town(slug="durham", name="Durham")
        self._staged_from_source("Ambiguous Show", town="", default_town=source_default)

        publish_all_approved(force_town=operator_choice)

        event = Event.objects.get(title="Ambiguous Show")
        self.assertEqual(event.town_id, operator_choice.id)

    def test_second_run_does_not_relog_an_already_skipped_row(self):
        """36.1's stated QA: a second consecutive pipeline run must not
        re-emit the 'no Town matches' warning for a row the first run already
        handled. Once skipped, the row is `skipped_no_town`, not `approved`,
        so the `status="approved"` queryset in publish_all_approved no longer
        selects it at all — the log line naturally fires zero times.
        """
        self._staged("Somewhere Else", "approved", town="Greensboro")

        with self.assertLogs("ingestion.services", level="WARNING") as cm:
            publish_all_approved()
        self.assertTrue(any("no Town matches" in msg for msg in cm.output))

        # Second run: nothing left in the `approved` queue for Greensboro, so no
        # logger call happens at all. assertNoLogs would be ideal but isn't
        # available on this Django's TestCase; assert the queryset is empty
        # and re-running is a no-op instead.
        self.assertEqual(
            StagedEvent.objects.filter(status="approved", town="Greensboro").count(), 0
        )
        result = publish_all_approved()
        self.assertEqual(result, {"published": 0, "already_published": 0, "removed": 0})
        self.assertEqual(StagedEvent.objects.get(title="Somewhere Else").status, "skipped_no_town")

    def test_skipped_row_is_still_a_dedupe_candidate(self):
        """A re-scrape of an already-skipped, out-of-coverage event must match
        the existing skipped_no_town row instead of creating a fresh row every
        poll — that would just trade one leak (retrying forever) for another
        (an unbounded pile of skipped duplicates). CANDIDATE_STATUSES includes
        skipped_no_town for exactly this reason.
        """
        original = self._staged("Somewhere Else", "approved", town="Greensboro")
        publish_all_approved()
        original.refresh_from_db()
        self.assertEqual(original.status, "skipped_no_town")

        rescraped = self._staged("Somewhere Else", "pending", town="Greensboro")
        dup = find_duplicate(rescraped)
        self.assertEqual(dup, original)

    def test_reopen_skipped_towns_command_reopens_matching_rows(self):
        """The chosen re-open strategy: coverage changes are not free anymore
        (unlike the old always-retry behavior) — an explicit management command
        must be run after adding a Town so previously-skipped rows return to
        `approved` for the next publish run to pick up. Rows whose town is still
        uncovered are left alone.
        """
        self._staged("Greensboro Show", "approved", town="Greensboro")
        publish_all_approved()
        self.assertEqual(StagedEvent.objects.get(title="Greensboro Show").status, "skipped_no_town")

        self._staged("Charlotte Show", "approved", town="Charlotte")
        publish_all_approved()
        self.assertEqual(StagedEvent.objects.get(title="Charlotte Show").status, "skipped_no_town")

        Town.objects.create(slug="greensboro", name="Greensboro")

        out = StringIO()
        call_command("reopen_skipped_towns", stdout=out)

        self.assertEqual(StagedEvent.objects.get(title="Greensboro Show").status, "approved")
        self.assertEqual(StagedEvent.objects.get(title="Charlotte Show").status, "skipped_no_town")
        self.assertIn("Reopened 1 of 2", out.getvalue())

        result = publish_all_approved()
        self.assertEqual(result["published"], 1)
        self.assertEqual(Event.objects.get(title="Greensboro Show").town.slug, "greensboro")


@tag("db")
class IngestDirectSubmissionTownMissTests(TestCase):
    """Ticket 36.7: the direct-submission town-miss branch (services.py, inside
    ingest_direct_submission) used to `return None` with no status change,
    leaving the StagedEvent stuck pending forever. It must now land terminal
    at status="skipped_no_town", mirroring the publish_all_approved sweep path
    (36.1) so the row is not a dead end and remains a dedupe anchor.
    """

    STD_PAYLOAD = {
        "title": "Out of Area Show",
        "description": "A show somewhere uncovered.",
        "location_name": "Some Venue",
        "town": "Greensboro",
        "tags": [],
        "price": 10,
    }

    def setUp(self):
        self.source = EventSource.objects.create(
            name="Direct Feed",
            source_type="ics",
            url="https://feed.test/direct.ics",
        )
        self.raw = RawEvent.objects.create(
            source=self.source,
            raw_title="Raw Out of Area Show",
            raw_description="A show",
            raw_location="Some Venue, Greensboro, NC",
            raw_start_datetime=START,
            source_url="",  # avoids fetch_page_text network call
            source_uid="direct-uid-greensboro",
        )
        # Greensboro is intentionally not seeded as a Town — out of coverage.
        self.user = make_user(user_type="BUSINESS")

    def _gemini_mocks(self, std_payload, score):
        """Same pattern as test_direct_ingest_db.py: a single patch with
        side_effect so standardize_event and score_event each get their own
        fake genai.Client() (both modules reference the same `genai` object).
        """
        fake_std = mock.Mock()
        fake_std.models.generate_content.return_value = mock.Mock(text=json.dumps(std_payload))
        fake_scorer = mock.Mock()
        fake_scorer.models.generate_content.return_value = mock.Mock(
            text=json.dumps({"score": score, "notes": ""})
        )
        return mock.patch(
            "ingestion.standardizer.genai.Client",
            side_effect=[fake_std, fake_scorer],
        )

    def test_out_of_coverage_town_lands_terminal_skipped_no_town(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            result = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(result)
        self.assertFalse(Event.objects.exists())
        staged = StagedEvent.objects.get()
        self.assertEqual(staged.status, "skipped_no_town")
        # No prior Event exists on a first submission — must stay unset.
        self.assertIsNone(staged.published_event)

    def test_resubmit_of_out_of_coverage_event_does_not_stack_rows(self):
        """ingest_direct_submission tears down the prior staged row for the
        same RawEvent at the top of the function (idempotency: re-standardize
        fresh) *before* find_duplicate runs, so the re-submit case here isn't
        "dedup blocks a second row" — it's "there is only ever one staged row
        per RawEvent, and it lands skipped_no_town again on each resubmit."
        The regression this guards is a second Event or a pile of duplicate
        staged rows, neither of which should happen.
        """
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            first = ingest_direct_submission(self.raw.id, self.user.id)
        self.assertIsNone(first)
        self.assertEqual(StagedEvent.objects.count(), 1)
        first_staged_id = StagedEvent.objects.get().id

        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            second = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(second)
        self.assertFalse(Event.objects.exists())
        self.assertEqual(StagedEvent.objects.count(), 1)
        staged = StagedEvent.objects.get()
        self.assertEqual(staged.status, "skipped_no_town")
        # The old row was torn down and a fresh one created (same RawEvent,
        # new pk) — not left stacked, and not silently reused either.
        self.assertNotEqual(staged.id, first_staged_id)

    def test_coverage_added_later_is_not_auto_reopened_by_direct_ingest(self):
        """reopen_skipped_towns has no source filter (confirmed out of scope
        for 36.7), so it already reopens direct-source rows once a Town is
        added — this just documents that ingest_direct_submission itself does
        not retry/reopen anything; the management command is the only path
        back to `approved` for a previously-skipped direct row.
        """
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            ingest_direct_submission(self.raw.id, self.user.id)
        staged = StagedEvent.objects.get()
        self.assertEqual(staged.status, "skipped_no_town")

        make_town(slug="greensboro", name="Greensboro")

        staged.refresh_from_db()
        self.assertEqual(staged.status, "skipped_no_town")


@tag("db")
class ResolveTownTests(TestCase):
    def test_valid_guess_wins_over_fallback(self):
        cary = make_town(slug="cary", name="Cary")
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self.assertEqual(resolve_town("Cary", raleigh), cary)

    def test_empty_guess_uses_fallback(self):
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self.assertEqual(resolve_town("", raleigh), raleigh)

    def test_unmatched_guess_uses_fallback(self):
        raleigh = make_town(slug="raleigh", name="Raleigh")
        self.assertEqual(resolve_town("Greensboro", raleigh), raleigh)

    def test_empty_guess_with_no_fallback_is_none(self):
        self.assertIsNone(resolve_town("", None))

    def test_unmatched_guess_with_no_fallback_is_none(self):
        self.assertIsNone(resolve_town("Greensboro", None))
