from asyncio import Event
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt


def index(request):
    return HttpResponse("Hello, world. You're at the events index.")

def getAll(request):
    #technically dont need everything, can reduce to increase performance
    #TODO: Needs specifc values to pull
    events_queryset = Event.objects.all().values()
    events_list = list(events_queryset)
    return JsonResponse(events_list, safe=False)

def getOne(request, event_id):
    event = Event.objects.filter(uuid=event_id).values().first()
    if event:
        return JsonResponse(event)
    else:
        return JsonResponse({'error': 'Event not found'}, status=404)

@csrf_exempt # Allows React to POST without a CSRF token
def createEvent(request):
    if request.method == 'POST':
        try:
            # 1. Parse the JSON sent from React
            data = json.loads(request.body)
            
            # 2. Create the Event object
            new_event = Event.objects.create(
                title=data['title'],
                city=data['city'],
                date=data['date'], # Ensure React sends "YYYY-MM-DD HH:MM" format
                venue_name=data['venue_name'],
                description=data['description'],
                # For price, we need to ensure it's a number or None
                price=data.get('price', 0.00)
            )
            
            # 3. Return success and the new UUID
            return JsonResponse({
                'status': 'success', 
                'uuid': new_event.uuid
            }, status=201)

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'error': 'Only POST method allowed'}, status=405)
