import logging
import os
from datetime import timedelta

from celery import shared_task
from django.template.loader import render_to_string
from django.utils import timezone

from events.email_service import send_email

logger = logging.getLogger(__name__)


@shared_task
def ping():
    return "pong"


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_one_digest(self, profile_id):
    """Render and send the personalized weekly digest to one UserProfile.

    Mirrors the per-profile body of the send_weekly_digest command: resolve the
    user's town, pull upcoming events for it, tag-filter against their interests,
    and email it. send_email swallows Brevo errors and returns False, so a falsy
    return triggers a retry (3x, 5-min backoff) without affecting other recipients.
    """
    from events.models import Event, Town, UserProfile

    profile = UserProfile.objects.select_related('user').prefetch_related('tags').filter(id=profile_id).first()
    if profile is None:
        logger.info("send_one_digest: profile %s no longer exists — skipping.", profile_id)
        return

    email = profile.user.email
    site_url = os.environ.get('SITE_URL', 'https://www.thecommons.town')
    subject = "The Commons — Your Weekly Digest"
    now = timezone.now()
    cutoff = now + timedelta(days=7)

    town = Town.objects.filter(slug=profile.primary_city).first()
    if town is None:
        logger.info("send_one_digest: %s primary_city %r matches no Town — skipping.", email, profile.primary_city)
        return

    events = (
        Event.objects
        .filter(date__gte=now, date__lte=cutoff, town=town)
        .prefetch_related('tags')
        .order_by('date')
    )

    user_tags = set(profile.tags.values_list('name', flat=True))
    if user_tags:
        events = [e for e in events if user_tags.intersection({t.name for t in e.tags.all()})]
    else:
        events = list(events)

    if not events:
        logger.info("send_one_digest: %s has no matching events this week — skipping.", email)
        return

    html = render_to_string('email/weekly_digest.html', {
        'events': events,
        'site_url': site_url,
        'subject': subject,
    })

    if send_email(email, subject, html):
        logger.info("send_one_digest: sent to %s (%d events).", email, len(events))
        return

    logger.warning("send_one_digest: send to %s failed — retrying.", email)
    raise self.retry()


@shared_task
def fan_out_weekly_digest():
    """Queue one send_one_digest subtask per WEEKLY subscriber. Returns the count."""
    from events.models import UserProfile

    profile_ids = list(
        UserProfile.objects.filter(email_preference='WEEKLY').values_list('id', flat=True)
    )
    for profile_id in profile_ids:
        send_one_digest.delay(profile_id)

    logger.info("fan_out_weekly_digest: queued %d digest subtasks.", len(profile_ids))
    return len(profile_ids)
