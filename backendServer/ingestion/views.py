from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from ingestion.services import publish_all_approved


@staff_member_required
def pipeline_docs(request):
    """Admin page: ingestion pipeline documentation."""
    return render(request, 'docs/pipeline_docs.html')


@staff_member_required
def admin_docs(request):
    """Admin page: admin backend documentation."""
    return render(request, 'docs/admin_docs.html')


@staff_member_required
def publish_approved_admin(request):
    """Admin page: manually publish all approved staged events."""
    result = None
    if request.method == 'POST':
        result = publish_all_approved()
    return render(request, 'docs/publish_approved.html', {'result': result})


@csrf_exempt
@require_GET
def cron_ingest(request):
    """Endpoint for Vercel cron to trigger the ingestion pipeline."""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {settings.CRON_SECRET}":
        return JsonResponse({'error': 'unauthorized'}, status=401)

    call_command('ingest_events')
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_POST
def publish_approved_events(request):
    """
    Atomically publishes all approved StagedEvents to the Events table,
    then removes them from the staged events table.

    If anything fails, the entire operation is rolled back.
    """
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {settings.THE_COMMONS_API_KEY}":
        return JsonResponse({'error': 'unauthorized'}, status=401)

    result = publish_all_approved()
    return JsonResponse({'status': 'ok', **result})
