"""Give the local dev DB one EventSource row per registered scraper.

The devtools playground's "load existing source" picker and its Probe button
both read EventSource rows, not the scraper registry — so on a fresh dev branch
(which only has the `direct` submission row) every scraper looks missing and the
only way to exercise one against a real source row is to deploy. This command
closes that gap by projecting the registry into rows, so a newly added scraper
module is testable locally as soon as it's wired into `scrapers/__init__.py`.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ingestion.models import EventSource
from ingestion.scraping.scrapers import list_scrapers


class Command(BaseCommand):
    help = "Seed dev database with an EventSource per registered scraper"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding even when DEBUG is off (e.g. prod settings)",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed: DEBUG is off, so this is likely the prod database. "
                "Use --force if you really mean it."
            )

        created_count = 0
        updated_count = 0
        for scraper in list_scrapers():
            if not scraper["url"]:
                self.stdout.write(
                    self.style.WARNING(f"Skipping {scraper['key']}: no url on the scraper class")
                )
                continue

            # Keyed on url to match `add_source`, so re-running is idempotent and
            # a row hand-made in the playground gets adopted rather than duplicated.
            _, created = EventSource.objects.update_or_create(
                url=scraper["url"],
                defaults={
                    "name": scraper["name"] or scraper["key"],
                    "source_type": scraper["source_type"],
                    "scraper_key": scraper["key"],
                    "active": True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(f"Created {created_count} sources, updated {updated_count} existing")
