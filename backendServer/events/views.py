from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Event, Town, UserProfile
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
    )

    return Response({'id': staged.id, 'status': staged.status}, status=status.HTTP_201_CREATED)


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
