import os
import logging
from datetime import timedelta
from django.utils import timezone
from django.template.loader import render_to_string

import brevo_python
from brevo_python.rest import ApiException

logger = logging.getLogger(__name__)


def _get_brevo_client():
    configuration = brevo_python.Configuration()
    configuration.api_key['api-key'] = os.environ['BREVO_API_KEY']
    return brevo_python.TransactionalEmailsApi(brevo_python.ApiClient(configuration))


def _build_recipients(frequency: str) -> list[dict]:
    """Return [{email, tags: set[str]}] for all subscribers of this frequency.

    UserProfile entries (authenticated users) take priority over
    NewsletterSubscriber rows when both share an email address. UserProfile
    subscribers get tag-filtered content; anonymous subscribers get everything.
    """
    from .models import UserProfile, NewsletterSubscriber

    pref_map = {'WEEKLY': 'WEEKLY', 'MONTHLY': 'MONTHLY'}
    db_pref = pref_map[frequency]

    # Authenticated users with a profile
    profiles = (
        UserProfile.objects
        .filter(email_preference=db_pref)
        .select_related('user')
        .prefetch_related('tags')
    )
    seen = {}
    for profile in profiles:
        email = profile.user.email.lower()
        seen[email] = {t.name for t in profile.tags.all()}

    # Anonymous newsletter subscribers — skip if already covered by a profile
    for sub in NewsletterSubscriber.objects.filter(frequency=frequency, is_active=True):
        email = sub.email.lower()
        if email not in seen:
            seen[email] = set()  # empty = no tag filter → send all events

    return [{'email': email, 'tags': tags} for email, tags in seen.items()]


def send_digest(frequency: str) -> dict:
    """Send the weekly or monthly digest to all active subscribers.

    Returns a dict with 'sent' and 'failed' counts.
    """
    from .models import Event

    if frequency == 'WEEKLY':
        cutoff = timezone.now() + timedelta(days=7)
        subject = "This Week in The Commons"
    else:
        cutoff = timezone.now() + timedelta(days=31)
        subject = "This Month in The Commons"

    all_events = list(
        Event.objects
        .filter(date__gte=timezone.now(), date__lte=cutoff)
        .select_related('town')
        .prefetch_related('tags')
        .order_by('date')
    )

    recipients = _build_recipients(frequency)
    if not recipients:
        logger.info("No active %s subscribers — skipping digest.", frequency)
        return {'sent': 0, 'failed': 0}

    client = _get_brevo_client()
    sender = brevo_python.SendSmtpEmailSender(
        name="The Commons",
        email=os.environ.get('DIGEST_FROM_EMAIL', 'digest@thecommons.town'),
    )
    site_url = os.environ.get('SITE_URL', 'https://www.thecommons.town')

    sent = failed = 0
    for recipient in recipients:
        tag_filter = recipient['tags']
        if tag_filter:
            events = [
                e for e in all_events
                if tag_filter.intersection({t.name for t in e.tags.all()})
            ]
        else:
            events = all_events

        html_body = render_to_string('email/digest.html', {
            'events': events,
            'frequency': frequency,
            'subject': subject,
            'site_url': site_url,
        })

        send_email = brevo_python.SendSmtpEmail(
            to=[brevo_python.SendSmtpEmailTo(email=recipient['email'])],
            sender=sender,
            subject=subject,
            html_content=html_body,
        )
        try:
            client.send_transac_email(send_email)
            sent += 1
        except ApiException as e:
            logger.error("Brevo send failed for %s: %s", recipient['email'], e)
            failed += 1

    logger.info("Digest sent: %d succeeded, %d failed.", sent, failed)
    return {'sent': sent, 'failed': failed}
