import os

from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone

from events.email_service import send_email


class Command(BaseCommand):
    help = "Render the weekly digest template with 5 upcoming events and send it to one address (for testing template + delivery)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            required=True,
            help='Address to send the test digest to.',
        )

    def handle(self, *args, **options):
        from events.models import Event

        to = options['email']
        site_url = os.environ.get('SITE_URL', 'https://www.thecommons.town')
        subject = "The Commons — Your Weekly Digest"

        events = list(
            Event.objects
            .filter(date__gte=timezone.now())
            .select_related('town')
            .prefetch_related('tags')
            .order_by('date')[:5]
        )

        if not events:
            self.stdout.write(self.style.WARNING(
                "No upcoming events found — sending the digest with an empty list."
            ))

        html = render_to_string('email/weekly_digest.html', {
            'events': events,
            'site_url': site_url,
            'subject': subject,
        })

        self.stdout.write(f"Sending test digest ({len(events)} events) to {to}...")
        if send_email(to, subject, html):
            self.stdout.write(self.style.SUCCESS(f"Sent test digest to {to}."))
        else:
            raise CommandError(f"Failed to send test digest to {to} — check logs and BREVO_API_KEY.")
