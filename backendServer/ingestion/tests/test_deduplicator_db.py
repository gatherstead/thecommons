from datetime import UTC, datetime, timedelta

from django.test import TestCase, tag

from ingestion.deduplicator import (
    BROADCAST_LOCATION_SIMILARITY_THRESHOLD,
    BROADCAST_TIME_WINDOW_HOURS,
    BROADCAST_TITLE_SIMILARITY_THRESHOLD,
    dedup_all_pending,
    find_duplicate,
)
from ingestion.models import EventSource, RawEvent, StagedEvent

START = datetime(2099, 6, 1, 18, 0, tzinfo=UTC)


@tag("db")
class DeduplicatorTests(TestCase):
    """find_duplicate/dedup_all_pending query StagedEvent, so these are DB-tier
    (the ticket's 'no ORM' framing isn't achievable against the real code)."""

    def _staged(self, title, location, start=START, status="pending"):
        return StagedEvent.objects.create(
            title=title,
            description="d",
            location_name=location,
            town="Carrboro",
            start_datetime=start,
            status=status,
        )

    def test_near_duplicate_is_collapsed(self):
        first = self._staged("Jazz Night at the Cradle", "Cat's Cradle")
        second = self._staged("Jazz Night at the Cradle", "Cat's Cradle")

        found = dedup_all_pending()

        self.assertEqual(found, 1)
        first.refresh_from_db()
        second.refresh_from_db()
        statuses = {first.status, second.status}
        self.assertEqual(statuses, {"duplicate", "pending"})
        dup = first if first.status == "duplicate" else second
        self.assertIsNotNone(dup.duplicate_of_id)

    def test_distinct_events_are_not_duplicates(self):
        anchor = self._staged("Jazz Night", "Cat's Cradle")
        other = self._staged("Farmers Market", "Town Commons")
        self.assertIsNone(find_duplicate(other))
        self.assertEqual(dedup_all_pending(), 0)
        anchor.refresh_from_db()
        self.assertEqual(anchor.status, "pending")

    def test_event_outside_time_window_is_not_duplicate(self):
        self._staged("Jazz Night", "Cat's Cradle")
        far = self._staged("Jazz Night", "Cat's Cradle", start=START + timedelta(hours=5))
        self.assertIsNone(find_duplicate(far))


@tag("db")
class BroadcastDedupeTests(TestCase):
    """The direct-submission / broadcast path, which uses the looser thresholds."""

    def setUp(self):
        self.source = EventSource.objects.create(
            name="Direct Host Submission", source_type="direct", url=""
        )
        self._uid = 0

    def _staged(self, title, location, *, raw_title=None, raw_location=None, start=START):
        """A staged row backed by a RawEvent, mirroring the direct-submit path."""
        self._uid += 1
        raw = RawEvent.objects.create(
            source=self.source,
            source_uid=f"draft-{self._uid}",
            raw_title=raw_title if raw_title is not None else title,
            raw_location=raw_location if raw_location is not None else location,
            raw_start_datetime=start,
            processed=True,
        )
        return StagedEvent.objects.create(
            raw_event=raw,
            title=title,
            description="d",
            location_name=location,
            town="Carrboro",
            start_datetime=start,
            status="pending",
        )

    def _find(self, staged):
        return find_duplicate(
            staged,
            title_threshold=BROADCAST_TITLE_SIMILARITY_THRESHOLD,
            location_threshold=BROADCAST_LOCATION_SIMILARITY_THRESHOLD,
            time_window_hours=BROADCAST_TIME_WINDOW_HOURS,
        )

    def test_divergent_llm_titles_over_identical_raw_titles_are_caught(self):
        """The prod miss: Gemini rewrote one submission's title beyond recognition.

        Two drafts carried the byte-identical raw title "The Wheelhouse Presents:
        Onyx Club Boys"; standardization turned one into "Onyx Club Boys Live at
        Fair Game Beverage Company". Scoring only the LLM titles gives 58 — under
        the 60 threshold — so both published. Scoring the raw titles too gives 100.
        """
        raw_title = "The Wheelhouse Presents: Onyx Club Boys"
        first = self._staged(
            "Onyx Club Boys Live at Fair Game Beverage Company",
            "Fair Game Beverage Company",
            raw_title=raw_title,
        )
        second = self._staged(
            "The Wheelhouse Presents: Onyx Club Boys",
            "Fair Game Beverage Company",
            raw_title=raw_title,
        )

        self.assertEqual(self._find(second), first)

    def test_presenter_suffix_variant_is_caught(self):
        first = self._staged("Meet The Maker: Raleigh Popsicle Co", "Fair Game Pantry")
        second = self._staged(
            "Meet The Maker: Raleigh Popsicle Co, Presented by Fair Game Pantry",
            "Fair Game Pantry",
        )
        self.assertEqual(self._find(second), first)

    def test_distinct_events_at_same_venue_are_not_duplicates(self):
        """Guard against the loosened thresholds collapsing a venue's whole calendar."""
        self._staged("Trivia Night", "Fair Game Beverage Company")
        other = self._staged("Sunday Farmers Market", "Fair Game Beverage Company")
        self.assertIsNone(self._find(other))

    def test_blank_location_does_not_veto_a_strong_title_match(self):
        first = self._staged("Fermentation Festival", "")
        second = self._staged("Fermentation Festival", "Fair Game Beverage Company")
        self.assertEqual(self._find(second), first)

    def test_corrected_start_time_still_matches_within_wider_window(self):
        first = self._staged("Fermentation Festival", "Fair Game")
        later = self._staged("Fermentation Festival", "Fair Game", start=START + timedelta(hours=8))
        self.assertEqual(self._find(later), first)

    def test_duplicate_rows_remain_candidates(self):
        """Once the original is published and swept, the duplicate is the only anchor."""
        first = self._staged("Fermentation Festival", "Fair Game")
        second = self._staged("Fermentation Festival", "Fair Game")
        second.status = "duplicate"
        second.duplicate_of = first
        second.save(update_fields=["status", "duplicate_of"])
        first.delete()

        third = self._staged("Fermentation Festival", "Fair Game")
        self.assertEqual(self._find(third), second)

    def test_pair_resolves_one_way_only(self):
        """Neither row may mark the other: mutual annihilation would drop the event."""
        first = self._staged("Fermentation Festival", "Fair Game")
        second = self._staged("Fermentation Festival", "Fair Game")

        self.assertIsNone(self._find(first))
        self.assertEqual(self._find(second), first)
