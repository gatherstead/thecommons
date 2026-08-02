import logging
import os
from datetime import timedelta

from django.template.loader import render_to_string
from django.utils import timezone

from events.email_service import send_email

logger = logging.getLogger(__name__)


def send_newsletter_welcome(email: str, manage_token) -> bool:
    """Send the welcome email for a new (or re-)subscription.

    Includes the login-free manage link keyed by the subscriber's manage_token.
    Best-effort — a Brevo failure here should never block the subscribe response.
    """
    manage_url = manage_url_for(manage_token)
    subject = "You're subscribed to The Commons"
    html = (
        "<p>Thanks for subscribing to The Commons newsletter.</p>"
        "<p>You can change your frequency or unsubscribe anytime, no login required, "
        f'at <a href="{manage_url}">{manage_url}</a>.</p>'
    )
    return send_email(email, subject, html)


def digest_window(frequency: str) -> tuple:
    """Return (cutoff, subject) for a digest frequency. Shared by send_digest
    and the per-recipient Celery task so the two paths can't drift apart.
    """
    if frequency == "WEEKLY":
        return timezone.now() + timedelta(days=7), "This Week in The Commons"
    return timezone.now() + timedelta(days=31), "This Month in The Commons"


def manage_url_for(manage_token) -> str:
    site_url = os.environ.get("SITE_URL", "https://www.thecommons.town")
    return f"{site_url}/newsletter/manage?token={manage_token}"


def _build_recipients(frequency: str) -> list[dict]:
    """Return [{email, tags: set[str], manage_token}] for all active subscribers.

    NewsletterSubscriber is the single source of truth for digest recipients —
    every row (anonymous or account-holding) carries a manage_token, so this is
    the only resolver that can produce a working manage/unsubscribe link. When
    a subscriber's email also has a UserProfile, its tags narrow the digest to
    matching events; otherwise (anonymous) the empty set sends everything.
    Both the Celery fan-out and the send_digest command call this — no
    divergent recipient logic anywhere else.
    """
    from accounts.models import UserProfile
    from newsletter.models import NewsletterSubscriber

    profile_tags_by_email = {
        profile.user.email.lower(): {t.name for t in profile.tags.all()}
        for profile in UserProfile.objects.select_related("user").prefetch_related("tags")
    }

    recipients = []
    for sub in NewsletterSubscriber.objects.filter(frequency=frequency, is_active=True):
        recipients.append(
            {
                "email": sub.email,
                "tags": profile_tags_by_email.get(sub.email.lower(), set()),
                "manage_token": sub.manage_token,
            }
        )
    return recipients


def send_digest(frequency: str) -> dict:
    """Send the weekly or monthly digest to all active subscribers.

    Returns a dict with 'sent' and 'failed' counts.
    """
    from events.models import Event

    cutoff, subject = digest_window(frequency)

    all_events = list(
        Event.objects.filter(date__gte=timezone.now(), date__lte=cutoff)
        .select_related("town")
        .prefetch_related("tags")
        .order_by("date")
    )

    recipients = _build_recipients(frequency)
    if not recipients:
        logger.info("No active %s subscribers — skipping digest.", frequency)
        return {"sent": 0, "failed": 0}

    site_url = os.environ.get("SITE_URL", "https://www.thecommons.town")

    sent = failed = 0
    for recipient in recipients:
        tag_filter = recipient["tags"]
        if tag_filter:
            events = [
                e for e in all_events if tag_filter.intersection({t.name for t in e.tags.all()})
            ]
        else:
            events = all_events

        html_body = render_to_string(
            "email/digest.html",
            {
                "events": events,
                "frequency": frequency,
                "subject": subject,
                "site_url": site_url,
                "manage_url": manage_url_for(recipient["manage_token"]),
            },
        )

        if send_email(recipient["email"], subject, html_body):
            sent += 1
        else:
            failed += 1

    logger.info("Digest sent: %d succeeded, %d failed.", sent, failed)
    return {"sent": sent, "failed": failed}
