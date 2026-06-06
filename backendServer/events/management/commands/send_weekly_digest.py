import logging
import os
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from events.email_service import send_email

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send the personalized weekly digest to every WEEKLY subscriber (their town + tag interests)."

    def handle(self, *args, **options):
        from events.models import Event, Town, UserProfile

        site_url = os.environ.get('SITE_URL', 'https://www.thecommons.town')
        subject = "The Commons — Your Weekly Digest"
        now = timezone.now()
        cutoff = now + timedelta(days=7)

        profiles = (
            UserProfile.objects
            .filter(email_preference='WEEKLY')
            .select_related('user')
            .prefetch_related('tags')
        )

        sent = skipped = failures = 0

        for profile in profiles:
            email = profile.user.email

            # primary_city is a CharField; resolve it to a Town via slug.
            town = Town.objects.filter(slug=profile.primary_city).first()
            if town is None:
                logger.info(
                    "Skipping %s: primary_city %r matches no Town.",
                    email, profile.primary_city,
                )
                skipped += 1
                continue

            events = (
                Event.objects
                .filter(date__gte=now, date__lte=cutoff, town=town)
                .prefetch_related('tags')
                .order_by('date')
            )

            user_tags = set(profile.tags.values_list('name', flat=True))
            if user_tags:
                events = [
                    e for e in events
                    if user_tags.intersection({t.name for t in e.tags.all()})
                ]
            else:
                events = list(events)

            if not events:
                logger.info("Skipping %s: no matching events this week.", email)
                skipped += 1
                continue

            html = render_to_string('email/weekly_digest.html', {
                'events': events,
                'site_url': site_url,
                'subject': subject,
            })

            if send_email(email, subject, html):
                logger.info("Sent weekly digest to %s (%d events).", email, len(events))
                sent += 1
            else:
                failures += 1

        summary = (
            f"Sent digest to {sent} users, {skipped} skipped (no events), {failures} failures."
        )
        logger.info(summary)
        self.stdout.write(self.style.SUCCESS(summary))
