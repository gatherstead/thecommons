from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Event, Town, UserProfile, NewsletterSubscriber
from .serializers import EventSerializer
from backend.permissions import BearerTokenAuthentication, HasCommonsAPIKeyOrUser
from ingestion.models import StagedEvent


@api_view(['GET'])
def getTowns(request):
    towns = Town.objects.all().order_by('name')
    return Response([{'slug': t.slug, 'name': t.name} for t in towns])


@api_view(['GET'])
def getAll(request):
    events = Event.objects.all().order_by('-date')

    include_past = request.query_params.get('include_past', '').lower() == 'true'

    after_param = request.query_params.get('after')
    if after_param:
        after_dt = parse_datetime(after_param)
        if after_dt:
            events = events.filter(date__gte=after_dt)
    elif not include_past:
        events = events.filter(date__gte=timezone.now())

    before_param = request.query_params.get('before')
    if before_param:
        before_dt = parse_datetime(before_param)
        if before_dt:
            events = events.filter(date__lte=before_dt)

    serializer = EventSerializer(events, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def getOne(request, event_id):
    event = get_object_or_404(Event, uuid=event_id)
    serializer = EventSerializer(event)
    return Response(serializer.data)


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
        'email_preference': profile.email_preference,
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

        if 'tags' in data:
            from .models import Tag
            tag_names = [t.strip().lower() for t in data['tags'] if t.strip()]
            tag_objs = []
            for name in tag_names:
                tag_obj, _ = Tag.objects.get_or_create(name=name)
                tag_objs.append(tag_obj)
            profile.tags.set(tag_objs)

        profile.save()

    return Response({
        'id': profile.user.id,
        'email': profile.user.email,
        'business_name': profile.user.name,
        'user_type': profile.user_type,
        'primary_city': profile.primary_city,
        'email_preference': profile.email_preference,
        'tags': [t.name for t in profile.tags.all()],
    })
