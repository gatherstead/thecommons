from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


@csrf_exempt
@require_GET
def cron_ingest(request):
    """Endpoint for Vercel cron to trigger the ingestion pipeline."""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {settings.CRON_SECRET}":
        return JsonResponse({'error': 'unauthorized'}, status=401)

    call_command('ingest_events')
    return JsonResponse({'status': 'ok'})
