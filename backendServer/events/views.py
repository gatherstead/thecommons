from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Event
from .serializers import EventSerializer
from backend.permissions import HasCommonsAPIKey
from ingestion.models import StagedEvent


@api_view(['GET'])
def getAll(request):
    # Query the database
    events = Event.objects.all().order_by('-date')
    
    # Serialize the data (many=True means we are converting a list, not just one item)
    serializer = EventSerializer(events, many=True)
    
    # Return the JSON data
    return Response(serializer.data)


@api_view(['GET'])
def getOne(request, event_id):
    # Get the object or return 404 automatically
    # Note: We use 'uuid' here because that's your model field name
    event = get_object_or_404(Event, uuid=event_id)
    
    # Serialize the single object
    serializer = EventSerializer(event)
    
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([HasCommonsAPIKey])
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