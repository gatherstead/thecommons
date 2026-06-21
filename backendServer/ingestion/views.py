from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from ingestion.tasks import publish_all_approved_task, run_ingestion_pipeline


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
    """Admin page: manually publish all approved staged events (runs in the background)."""
    queued = False
    if request.method == 'POST':
        publish_all_approved_task.delay()
        queued = True
    return render(request, 'docs/publish_approved.html', {'queued': queued})


@csrf_exempt
@require_GET
def cron_ingest(request):
    """Endpoint for cron to trigger the ingestion pipeline (runs async on a worker)."""
    auth = request.headers.get('Authorization', '')
    if auth != f"Bearer {settings.CRON_SECRET}":
        return JsonResponse({'error': 'unauthorized'}, status=401)

    result = run_ingestion_pipeline.delay()
    return JsonResponse({'status': 'queued', 'task_id': result.id}, status=202)


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

    result = publish_all_approved_task.delay()
    return JsonResponse({'status': 'queued', 'task_id': result.id}, status=202)
