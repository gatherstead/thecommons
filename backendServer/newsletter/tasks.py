import logging
import os

from celery import shared_task
from django.template.loader import render_to_string
from django.utils import timezone

from events.email_service import send_email
from newsletter.email_service import _build_recipients, digest_window, manage_url_for

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_one_digest(self, email, tags, manage_token, frequency):
    """Render and send the personalized digest to one resolved recipient.

    Takes an already-resolved recipient (email/tags/manage_token/frequency)
    rather than a UserProfile id, so it serves both authenticated and
    anonymous NewsletterSubscriber rows alike — the fan-out tasks are the only
    callers, and both go through email_service._build_recipients first. `tags`
    arrives as a list (Celery JSON-serializes task args) and is treated as a
    set of interest-tag names to filter events by; an empty list sends
    everything. send_email swallows Brevo errors and returns False, so a
    falsy return triggers a retry (3x, 5-min backoff) without affecting other
    recipients.
    """
    from events.models import Event

    tag_filter = set(tags)
    now = timezone.now()
    cutoff, subject = digest_window(frequency)

    events = (
        Event.objects.filter(date__gte=now, date__lte=cutoff)
        .select_related("town")
        .prefetch_related("tags")
        .order_by("date")
    )
    if tag_filter:
        events = [e for e in events if tag_filter.intersection({t.name for t in e.tags.all()})]
    else:
        events = list(events)

    if not events:
        logger.info("send_one_digest: %s has no matching events — skipping.", email)
        return

    site_url = os.environ.get("SITE_URL", "https://www.thecommons.town")
    html = render_to_string(
        "email/digest.html",
        {
            "events": events,
            "frequency": frequency,
            "subject": subject,
            "site_url": site_url,
            "manage_url": manage_url_for(manage_token),
        },
    )

    if send_email(email, subject, html):
        logger.info("send_one_digest: sent to %s (%d events).", email, len(events))
        return

    logger.warning("send_one_digest: send to %s failed — retrying.", email)
    raise self.retry()


def _queue_digest_fan_out(frequency):
    recipients = _build_recipients(frequency)
    for recipient in recipients:
        send_one_digest.delay(
            recipient["email"],
            list(recipient["tags"]),
            str(recipient["manage_token"]),
            frequency,
        )
    logger.info("fan_out_%s_digest: queued %d digest subtasks.", frequency.lower(), len(recipients))
    return len(recipients)


@shared_task
def fan_out_weekly_digest():
    """Queue one send_one_digest subtask per WEEKLY subscriber. Returns the count."""
    return _queue_digest_fan_out("WEEKLY")


@shared_task
def fan_out_monthly_digest():
    """Queue one send_one_digest subtask per MONTHLY subscriber. Returns the count."""
    return _queue_digest_fan_out("MONTHLY")
