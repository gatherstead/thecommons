"""Plain-function test factories (no factory_boy — house style).

Every helper takes keyword overrides and returns a saved instance, so tests
read top-down without per-class setup boilerplate.
"""
import uuid
from datetime import timedelta

from django.utils import timezone

from events.models import BetterAuthUser, Event, Town, UserProfile


def make_user(user_type='LOCAL', email=None, **profile_kwargs):
    """Create a neon_auth `user` row plus its UserProfile. Extra kwargs
    (e.g. email_preference, primary_city) go to the profile.
    """
    now = timezone.now()
    user = BetterAuthUser.objects.create(
        id=uuid.uuid4(),
        name='Test',
        email=email or f'{uuid.uuid4().hex}@example.com',
        created_at=now,
        updated_at=now,
        user_type=user_type,
    )
    UserProfile.objects.create(user=user, user_type=user_type, **profile_kwargs)
    return user


def make_town(slug='carrboro', name=None):
    # get_or_create: migration 0004 seeds 'carrboro' into the test DB already.
    town, _ = Town.objects.get_or_create(
        slug=slug, defaults={'name': name or slug.replace('-', ' ').title()}
    )
    return town


def make_event(title='Test Event', town=None, days_offset=1, **overrides):
    fields = {
        'title': title,
        'town': town or make_town(),
        'date': timezone.now() + timedelta(days=days_offset),
        'venue': 'Venue',
        'description': 'desc',
    }
    fields.update(overrides)
    return Event.objects.create(**fields)
