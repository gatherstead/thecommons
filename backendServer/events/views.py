from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Event
from .serializers import EventSerializer


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
def createEvent(request):
    # Pass the JSON data (request.data) to the serializer
    serializer = EventSerializer(data=request.data)
    
    # Validate the data (this runs the logic in your serializers.py)
    if serializer.is_valid():
        # Save to database
        serializer.save()
        # Return success with the new data
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    # If invalid, return the errors (e.g., "Price must be a number")
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)