from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from events.models import Town
from ingestion.models import EventSource


class Command(BaseCommand):
    help = "Register or update an event source for daily ingestion."

    def add_arguments(self, parser):
        parser.add_argument("--url", required=True, help="Source URL")
        parser.add_argument(
            "--type",
            dest="source_type",
            default="ics",
            choices=["ics", "scraper", "http"],
            help="Source type (default: ics)",
        )
        parser.add_argument("--name", required=True, help="Human-readable source name")
        parser.add_argument(
            "--scraper-key", default="", help="Scraper key (scraper/http types only)"
        )
        parser.add_argument(
            "--prompt-suffix", default="", help="Optional suffix appended to Gemini prompts"
        )
        parser.add_argument(
            "--default-town",
            default="",
            help=(
                "Slug of the Town to fall back to when Gemini returns a blank "
                "per-event town (see ingestion.services.resolve_town). Fallback "
                "only -- a per-event guess that resolves to a different known "
                "Town is never overridden."
            ),
        )
        parser.add_argument(
            "--blocked-reason",
            default="",
            help="Set to mark this source known-blocked (e.g. a vendor WAF)."
            " Quarantines it in the monitor without disabling polling.",
        )

    def handle(self, *args, **options):
        url = options["url"]
        source_type = options["source_type"]
        name = options["name"]
        scraper_key = options["scraper_key"] if source_type in ("scraper", "http") else ""
        prompt_suffix = options["prompt_suffix"]
        blocked_reason = options["blocked_reason"]

        if source_type in ("scraper", "http") and not scraper_key:
            raise CommandError(f"--scraper-key is required for source type '{source_type}'")

        default_town = None
        default_town_slug = options["default_town"]
        if default_town_slug:
            try:
                default_town = Town.objects.get(slug=default_town_slug)
            except Town.DoesNotExist as err:
                raise CommandError(
                    f"--default-town '{default_town_slug}' is not a known Town"
                ) from err

        defaults = {
            "name": name,
            "source_type": source_type,
            "active": True,
            "scraper_key": scraper_key,
            "prompt_suffix": prompt_suffix,
            "blocked_reason": blocked_reason,
        }
        if default_town is not None:
            defaults["default_town"] = default_town
        # blocked_since tracks when quarantine started; only stamped the first
        # time --blocked-reason is set on a source that wasn't already
        # blocked, so re-running add_source doesn't keep resetting the clock.
        if blocked_reason:
            existing = EventSource.objects.filter(url=url).first()
            if existing is None or not existing.blocked_reason:
                defaults["blocked_since"] = timezone.now().date()
        else:
            defaults["blocked_since"] = None

        source, created = EventSource.objects.update_or_create(
            url=url,
            defaults=defaults,
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb}: {source.name} ({source.source_type}) — id={source.id}")
        )
