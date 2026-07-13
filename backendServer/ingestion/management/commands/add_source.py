from django.core.management.base import BaseCommand, CommandError

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

    def handle(self, *args, **options):
        url = options["url"]
        source_type = options["source_type"]
        name = options["name"]
        scraper_key = options["scraper_key"] if source_type in ("scraper", "http") else ""
        prompt_suffix = options["prompt_suffix"]

        if source_type in ("scraper", "http") and not scraper_key:
            raise CommandError(f"--scraper-key is required for source type '{source_type}'")

        source, created = EventSource.objects.update_or_create(
            url=url,
            defaults={
                "name": name,
                "source_type": source_type,
                "active": True,
                "scraper_key": scraper_key,
                "prompt_suffix": prompt_suffix,
            },
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb}: {source.name} ({source.source_type}) — id={source.id}")
        )
