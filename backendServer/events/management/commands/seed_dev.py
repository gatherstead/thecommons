from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from events.models import Category, Event, Tag, Town


TOWNS = [
    ('carrboro', 'Carrboro'),
    ('chapel-hill', 'Chapel Hill'),
    ('hillsborough', 'Hillsborough'),
    ('durham', 'Durham'),
    ('pittsboro', 'Pittsboro'),
]

TAGS = [
    'Music', 'Food & Drink', 'Arts', 'Community', 'Outdoors',
    'Family', 'Sports', 'Tech', 'Wellness', 'Nightlife',
]

CATEGORIES = [
    ('concerts', 'Concerts'),
    ('food', 'Food & Drink'),
    ('community', 'Community'),
    ('arts', 'Arts & Culture'),
    ('outdoors', 'Outdoors'),
    ('family', 'Family'),
]

EVENTS = [
    {
        'title': "Live Music at Cat's Cradle: Local Indie Night",
        'town_slug': 'carrboro',
        'venue': "Cat's Cradle",
        'description': (
            "An evening of local indie bands taking the stage at the legendary Cat's Cradle. "
            "Three acts, full bar, all ages welcome until 10 PM."
        ),
        'days_offset': 3,
        'tags': ['Music', 'Nightlife'],
        'categories': ['concerts'],
        'price': '12.00',
    },
    {
        'title': "Carrboro Farmers Market — Summer Opening",
        'town_slug': 'carrboro',
        'venue': 'Carrboro Town Commons',
        'description': (
            "The Carrboro Farmers Market opens for the summer season. Over 60 local vendors "
            "selling produce, cheese, baked goods, and handmade crafts. Rain or shine."
        ),
        'days_offset': 5,
        'tags': ['Food & Drink', 'Community', 'Family'],
        'categories': ['food', 'community'],
        'price': None,
    },
    {
        'title': "Ackland Art Museum: Community Gallery Night",
        'town_slug': 'chapel-hill',
        'venue': 'Ackland Art Museum',
        'description': (
            "Free admission evening at the Ackland featuring rotating works from Triangle-area "
            "artists. Wine and light refreshments provided."
        ),
        'days_offset': 7,
        'tags': ['Arts', 'Community'],
        'categories': ['arts'],
        'price': '0.00',
    },
    {
        'title': "Eno River Trail Cleanup & Hike",
        'town_slug': 'hillsborough',
        'venue': 'Eno River State Park — Cole Mill Access',
        'description': (
            "Join Friends of Eno River for a morning trail cleanup followed by a guided 4-mile "
            "hike. Gloves and bags provided. Bring water and sturdy shoes."
        ),
        'days_offset': 10,
        'tags': ['Outdoors', 'Community'],
        'categories': ['outdoors', 'community'],
        'price': None,
    },
    {
        'title': "Durham Bulls vs. Charlotte Knights — Fireworks Night",
        'town_slug': 'durham',
        'venue': 'Durham Bulls Athletic Park',
        'description': (
            "Triple-A baseball under the lights followed by a post-game fireworks show. "
            "Family-friendly seating sections available."
        ),
        'days_offset': 12,
        'tags': ['Sports', 'Family'],
        'categories': ['family'],
        'price': '14.00',
    },
    {
        'title': "Pittsboro Pepper Festival",
        'town_slug': 'pittsboro',
        'venue': 'Downtown Pittsboro Courthouse Square',
        'description': (
            "Celebrate the heat with local hot sauce vendors, pepper tastings, live bluegrass, "
            "and a jalapeño eating contest. Free entry."
        ),
        'days_offset': 16,
        'tags': ['Food & Drink', 'Music', 'Community'],
        'categories': ['food', 'community'],
        'price': '0.00',
    },
    {
        'title': "Triangle Tech Meetup: AI & Local Communities",
        'town_slug': 'chapel-hill',
        'venue': "Frankie's Fun Park Conference Room",
        'description': (
            "Monthly Triangle Tech Meetup — this month's topic: applying AI tools to local "
            "civic projects. Lightning talks, networking, free pizza."
        ),
        'days_offset': 19,
        'tags': ['Tech', 'Community'],
        'categories': ['community'],
        'price': None,
    },
    {
        'title': "Saturday Morning Yoga in the Park",
        'town_slug': 'carrboro',
        'venue': 'Anderson Community Park',
        'description': (
            "All-levels outdoor yoga session led by a certified instructor. "
            "Bring your own mat. Sessions run rain-or-shine under the pavilion."
        ),
        'days_offset': 22,
        'tags': ['Wellness', 'Outdoors', 'Family'],
        'categories': ['outdoors'],
        'price': '5.00',
    },
]


class Command(BaseCommand):
    help = 'Seed dev database with Towns, Tags, Categories, and sample Events'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Allow seeding even when DEBUG is off (e.g. prod settings)',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force']:
            raise CommandError(
                'Refusing to seed: DEBUG is off, so this is likely the prod database. '
                'Use --force if you really mean it.'
            )

        now = timezone.now()

        towns_created = 0
        town_map = {}
        for slug, name in TOWNS:
            obj, created = Town.objects.get_or_create(slug=slug, defaults={'name': name})
            town_map[slug] = obj
            if created:
                towns_created += 1

        tags_created = 0
        tag_map = {}
        for name in TAGS:
            obj, created = Tag.objects.get_or_create(name=name)
            tag_map[name] = obj
            if created:
                tags_created += 1

        cats_created = 0
        cat_map = {}
        for slug, display_name in CATEGORIES:
            obj, created = Category.objects.get_or_create(slug=slug, defaults={'display_name': display_name})
            cat_map[slug] = obj
            if created:
                cats_created += 1

        events_created = 0
        events_existing = 0
        for spec in EVENTS:
            if Event.objects.filter(title=spec['title']).exists():
                events_existing += 1
                continue

            event = Event.objects.create(
                title=spec['title'],
                town=town_map[spec['town_slug']],
                date=now + timedelta(days=spec['days_offset']),
                venue=spec['venue'],
                description=spec['description'],
                price=spec.get('price'),
                created_by=None,
                source_name='seed_dev',
            )
            event.tags.set([tag_map[t] for t in spec['tags']])
            event.categories.set([cat_map[c] for c in spec['categories']])
            events_created += 1

        self.stdout.write(
            f'Created {towns_created} towns, {tags_created} tags, '
            f'{cats_created} categories, {events_created} events '
            f'({events_existing} already existed)'
        )
        self.stdout.write('To create test users, sign up at http://localhost:3000/auth')
