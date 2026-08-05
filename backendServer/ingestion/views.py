from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from backend.permissions import BearerTokenAuthentication
from ingestion.models import EventSource, RawEvent
from ingestion.serializers import DirectSubmitEventSerializer
from ingestion.tasks import (
    ingest_direct_submission_task,
    publish_all_approved_task,
    run_ingestion_pipeline,
)


@staff_member_required
def pipeline_docs(request):
    """Admin page: ingestion pipeline documentation."""
    return render(request, "docs/pipeline_docs.html")


@staff_member_required
def admin_docs(request):
    """Admin page: admin backend documentation."""
    return render(request, "docs/admin_docs.html")


@staff_member_required
def publish_approved_admin(request):
    """Admin page: manually publish all approved staged events (runs in the background)."""
    queued = False
    if request.method == "POST":
        publish_all_approved_task.delay()
        queued = True
    return render(request, "docs/publish_approved.html", {"queued": queued})


@csrf_exempt
@require_GET
def cron_ingest(request):
    """Endpoint for cron to trigger the ingestion pipeline (runs async on a worker)."""
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {settings.CRON_SECRET}":
        return JsonResponse({"error": "unauthorized"}, status=401)

    result = run_ingestion_pipeline.delay()
    return JsonResponse({"status": "queued", "task_id": result.id}, status=202)


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([])
def direct_submit(request):
    """Accept a direct host event submission, upsert a RawEvent, and enqueue processing.

    Attribute to the caller's Better Auth JWT when present; accept anonymous
    submissions (owner = None) otherwise.  Invalid tokens are rejected with 401
    by BearerTokenAuthentication before this view body runs.
    """
    user_id = request.user.id if getattr(request.user, "is_authenticated", False) else None

    serializer = DirectSubmitEventSerializer(data=request.data.get("event", {}))
    if not serializer.is_valid():
        return Response({"event": serializer.errors}, status=400)

    draft_id = request.data.get("draft_id")
    if not draft_id:
        return Response({"draft_id": "required"}, status=400)

    source, _ = EventSource.objects.get_or_create(
        name="Direct Host Submission",
        source_type="direct",
        defaults={"url": "", "active": False},
    )

    data = serializer.validated_data
    raw_location = ", ".join(p for p in [data["venue_name"], data["address_line1"]] if p)[:500]

    raw_event, _ = RawEvent.objects.update_or_create(
        source=source,
        source_uid=str(draft_id),
        defaults={
            "raw_title": data["title"][:500],
            "raw_description": data["description"],
            "raw_location": raw_location,
            "raw_start_datetime": data["start_datetime"],
            "raw_end_datetime": data.get("end_datetime"),
            "source_url": data.get("event_url", "")[:500],
            "raw_organizer": data["organizer_name"][:200],
            # Stored verbatim, unvalidated — mirrors raw_organizer's "as
            # submitted" idiom. The broadcast SPA's category vocabulary isn't
            # guaranteed to match CATEGORY_SLUGS, so filtering against the
            # canonical vocabulary happens once, in standardize_event, rather
            # than here (an `update_or_create` on every resubmission would
            # otherwise re-filter the same list for no reason).
            "raw_categories": data["categories"],
            "processed": False,
        },
    )

    ingest_direct_submission_task.delay(raw_event.id, user_id)

    return Response({"status": "queued", "draft_id": str(draft_id)}, status=202)


@csrf_exempt
@require_POST
def publish_approved_events(request):
    """
    Atomically publishes all approved StagedEvents to the Events table,
    then removes them from the staged events table.

    If anything fails, the entire operation is rolled back.
    """
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {settings.THE_COMMONS_API_KEY}":
        return JsonResponse({"error": "unauthorized"}, status=401)

    result = publish_all_approved_task.delay()
    return JsonResponse({"status": "queued", "task_id": result.id}, status=202)
