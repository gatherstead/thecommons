from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from .models import Event, Town, Category, UserProfile, NewsletterSubscriber, BetterAuthAccount, BusinessProfile
from .serializers import EventSerializer, BusinessProfileSerializer
from . import cache as events_cache
from backend.permissions import BearerTokenAuthentication, HasCommonsAPIKeyOrUser
from ingestion.models import StagedEvent

PAGE_SIZE = 30


def user_has_password(user_id):
    """True when the user has a Better Auth credential account with a password set.

    Lazy (passwordless) accounts are created via the internal adapter with no
    credential row, so this distinguishes secured accounts from unsecured ones.
    """
    return BetterAuthAccount.objects.filter(
        user_id=str(user_id), provider_id='credential', password__isnull=False
    ).exists()


class EventsPagination(PageNumberPagination):
    page_size = PAGE_SIZE
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
def getTowns(request):
    data = cache.get(events_cache.TOWNS_CACHE_KEY)
    if data is None:
        towns = Town.objects.all().order_by('name')
        data = [{'slug': t.slug, 'name': t.name} for t in towns]
        cache.set(events_cache.TOWNS_CACHE_KEY, data, events_cache.STATIC_TTL)
    return Response(data)


@api_view(['GET'])
def getCategories(request):
    data = cache.get(events_cache.CATEGORIES_CACHE_KEY)
    if data is None:
        cats = Category.objects.all().order_by('display_name')
        data = [{'slug': c.slug, 'display_name': c.display_name} for c in cats]
        cache.set(events_cache.CATEGORIES_CACHE_KEY, data, events_cache.STATIC_TTL)
    return Response(data)


@api_view(['GET'])
def getAll(request):
    """
    List published events (paginated, page_size=30).

    Query params (applied in priority order — after/before/include_past override window):
      after        ISO datetime — events on or after this datetime
      before       ISO datetime — events on or before this datetime
      include_past bool        — include all past events (no lower bound)
      window       default | past | future
                   default: now <= date <= now + 90 days if ≥30 events exist there,
                            otherwise date >= now (fills page from all future events)
                   past:    date < now
                   future:  date > now + 90 days
    """
    cache_key = events_cache.events_list_key(request.query_params)
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    now = timezone.now()
    ninety_days_out = now + timedelta(days=90)

    events = Event.objects.all().order_by('date')

    include_past = request.query_params.get('include_past', '').lower() == 'true'
    after_param = request.query_params.get('after')
    before_param = request.query_params.get('before')
    window = request.query_params.get('window', '').lower()

    # after/before/include_past are explicit overrides; window applies only when none are set
    if after_param or before_param or include_past:
        if after_param:
            after_dt = parse_datetime(after_param)
            if after_dt:
                events = events.filter(date__gte=after_dt)
        elif not include_past:
            events = events.filter(date__gte=now)

        if before_param:
            before_dt = parse_datetime(before_param)
            if before_dt:
                events = events.filter(date__lte=before_dt)
    else:
        if window == 'past':
            events = events.filter(date__lt=now).order_by('-date')
        elif window == 'future':
            events = events.filter(date__gt=ninety_days_out)
        else:  # 'default' or unset — 90-day cap unless fewer than PAGE_SIZE events exist there
            qs_90 = events.filter(date__gte=now, date__lte=ninety_days_out)
            if qs_90.count() >= PAGE_SIZE:
                events = qs_90
            else:
                events = events.filter(date__gte=now)

    category_param = request.query_params.getlist('category')
    if category_param:
        events = events.filter(categories__slug__in=category_param).distinct()

    paginator = EventsPagination()
    page = paginator.paginate_queryset(events, request)
    serializer = EventSerializer(page, many=True)
    data = paginator.get_paginated_response(serializer.data).data
    cache.set(cache_key, data, events_cache.EVENTS_LIST_TTL)
    return Response(data)


@api_view(['GET', 'DELETE'])
@authentication_classes([BearerTokenAuthentication])
def getOne(request, event_id):
    event = get_object_or_404(Event, uuid=event_id)
    if request.method == 'DELETE':
        if not getattr(request.user, 'is_authenticated', False):
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        if event.created_by_id != request.user.id:
            return Response({'error': 'You can only delete your own events.'}, status=status.HTTP_403_FORBIDDEN)
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = EventSerializer(event)
    return Response(serializer.data)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def manageStagedEvent(request, event_id):
    staged = get_object_or_404(StagedEvent, id=event_id, submitted_by=request.user)

    if request.method == 'DELETE':
        staged.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if request.method == 'GET':
        return Response({
            'id': staged.id,
            'title': staged.title,
            'venue': staged.location_name,
            'town': staged.town,
            'date': staged.start_datetime.isoformat() if staged.start_datetime else None,
            'description': staged.description,
            'price': str(staged.price) if staged.price is not None else '',
            'link': staged.link,
            'tags': staged.tags,
            'status': staged.status,
        })

    # PATCH
    data = request.data
    if 'title' in data:
        staged.title = data['title']
    if 'venue' in data:
        staged.location_name = data['venue']
    if 'town' in data:
        staged.town = data['town']
    if 'date' in data:
        dt = parse_datetime(data['date'])
        if dt:
            staged.start_datetime = dt
    if 'description' in data:
        staged.description = data['description']
    if 'price' in data:
        staged.price = data['price'] or None
    if 'link' in data:
        staged.link = data['link']
    if 'tags' in data:
        staged.tags = data['tags']
    if 'category' in data:
        staged.category = data['category']
    staged.save()
    return Response({'id': staged.id, 'status': staged.status})


@api_view(['POST'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([HasCommonsAPIKeyOrUser])
def createEvent(request):
    data = request.data

    required = ['title', 'town', 'venue', 'date', 'description']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return Response({'error': f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

    submitted_by = request.user if getattr(request.user, 'is_authenticated', False) else None

    staged = StagedEvent.objects.create(
        title=data['title'],
        town=data['town'],
        location_name=data['venue'],
        start_datetime=data['date'],
        description=data['description'],
        price=data.get('price') or None,
        link=data.get('link', ''),
        tags=data.get('tags', []),
        category=data.get('category', ''),
        status='pending',
        submitted_by=submitted_by,
    )

    return Response({'id': staged.id, 'status': staged.status}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def getMyEvents(request):
    user = request.user

    staged_qs = StagedEvent.objects.filter(submitted_by=user).order_by('-created_at')
    published_qs = Event.objects.filter(created_by=user).order_by('-date')

    results = []

    for s in staged_qs:
        results.append({
            'id': str(s.id),
            'title': s.title,
            'date': s.start_datetime.isoformat() if s.start_datetime else None,
            'venue': s.location_name,
            'status': s.status,
        })

    for e in published_qs:
        results.append({
            'id': str(e.uuid),
            'title': e.title,
            'date': e.date.isoformat() if e.date else None,
            'venue': e.venue,
            'status': 'published',
        })

    results.sort(key=lambda x: x['date'] or '', reverse=True)

    return Response(results)


def _account_type(user_id):
    """The authoritative account type lives on UserProfile, not BetterAuthUser."""
    return (
        UserProfile.objects
        .filter(user_id=user_id)
        .values_list('user_type', flat=True)
        .first()
    )


@api_view(['GET', 'POST'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def businesses(request):
    account_type = _account_type(request.user.id)

    if request.method == 'GET':
        if account_type != 'VENUE':
            return Response(
                {'error': 'Only venue accounts can browse the business directory.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = BusinessProfile.objects.filter(is_published=True).prefetch_related('tags', 'service_area')

        tag = request.query_params.get('tag')
        if tag:
            qs = qs.filter(tags__name=tag.strip().lower())

        service_area = request.query_params.get('service_area')
        if service_area:
            qs = qs.filter(service_area__slug=service_area.strip())

        q = request.query_params.get('q')
        if q:
            qs = qs.filter(business_name__icontains=q)

        qs = qs.distinct().order_by('business_name')
        return Response(BusinessProfileSerializer(qs, many=True).data)

    # POST
    if account_type != 'BUSINESS':
        return Response(
            {'error': 'Only business accounts can create a listing.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if BusinessProfile.objects.filter(user_id=request.user.id).exists():
        return Response(
            {'error': 'You already have a business listing.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = BusinessProfileSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save(user=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def my_business(request):
    business = (
        BusinessProfile.objects
        .filter(user_id=request.user.id)
        .prefetch_related('tags', 'service_area')
        .first()
    )
    if business is None:
        return Response({'detail': 'No business listing.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(BusinessProfileSerializer(business).data)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def business_detail(request, business_id):
    business = get_object_or_404(BusinessProfile, uuid=business_id)
    is_owner = business.user_id == request.user.id

    if request.method == 'GET':
        if not is_owner and _account_type(request.user.id) != 'VENUE':
            return Response(
                {'error': 'You do not have access to this listing.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(BusinessProfileSerializer(business).data)

    if not is_owner:
        return Response(
            {'error': 'You can only modify your own listing.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == 'DELETE':
        business.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = BusinessProfileSerializer(business, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
def subscribe(request):
    email = request.data.get('email', '').strip().lower()
    frequency = request.data.get('frequency', 'WEEKLY').upper()

    if not email:
        return Response({'error': 'email is required'}, status=status.HTTP_400_BAD_REQUEST)

    if frequency not in ('WEEKLY', 'MONTHLY'):
        return Response({'error': 'frequency must be WEEKLY or MONTHLY'}, status=status.HTTP_400_BAD_REQUEST)

    subscriber, created = NewsletterSubscriber.objects.update_or_create(
        email=email,
        defaults={'frequency': frequency, 'is_active': True},
    )

    return Response(
        {'email': subscriber.email, 'frequency': subscriber.frequency},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['GET'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def getMyProfile(request):
    profile = UserProfile.objects.filter(user_id=request.user.id).select_related('user').first()
    if profile is None:
        return Response({'detail': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        'id': profile.user.id,
        'email': profile.user.email,
        'business_name': profile.user.name,
        'user_type': profile.user_type,
        'primary_city': profile.primary_city,
        'address': profile.address,
        'email_preference': profile.email_preference,
        'has_password': user_has_password(profile.user.id),
    })


@api_view(['GET', 'PATCH'])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    profile = (
        UserProfile.objects
        .filter(user_id=request.user.id)
        .select_related('user')
        .prefetch_related('tags')
        .first()
    )
    if profile is None:
        return Response({'detail': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        data = request.data

        if 'email_preference' in data:
            pref = data['email_preference'].upper()
            if pref not in ('WEEKLY', 'MONTHLY', 'NEVER'):
                return Response(
                    {'error': 'email_preference must be WEEKLY, MONTHLY, or NEVER'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.email_preference = pref

        if 'user_type' in data:
            new_type = data['user_type'].upper()
            if new_type not in ('BUSINESS', 'VENUE'):
                return Response(
                    {'error': 'user_type can only be changed to BUSINESS or VENUE'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if profile.user_type == 'LOCAL':
                return Response(
                    {'error': 'Cannot change account type from LOCAL'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.user_type = new_type

        if 'primary_city' in data:
            profile.primary_city = data['primary_city']

        if 'address' in data:
            profile.address = data['address']

        if 'tags' in data:
            from .models import Tag
            tag_names = [t.strip().lower() for t in data['tags'] if t.strip()]
            tag_objs = []
            for name in tag_names:
                tag_obj, _ = Tag.objects.get_or_create(name=name)
                tag_objs.append(tag_obj)
            profile.tags.set(tag_objs)

        profile.save()

        email = (profile.user.email or '').strip().lower()
        if email:
            if profile.email_preference in ('WEEKLY', 'MONTHLY'):
                NewsletterSubscriber.objects.update_or_create(
                    email=email,
                    defaults={'frequency': profile.email_preference, 'is_active': True},
                )
            else:
                NewsletterSubscriber.objects.filter(email=email).delete()

    return Response({
        'id': profile.user.id,
        'email': profile.user.email,
        'business_name': profile.user.name,
        'user_type': profile.user_type,
        'primary_city': profile.primary_city,
        'address': profile.address,
        'email_preference': profile.email_preference,
        'tags': [t.name for t in profile.tags.all()],
        'has_password': user_has_password(profile.user.id),
    })
