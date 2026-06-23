"""Broadcast API views. Thin — eligibility in routing.py, persistence in services.py.

No global REST_FRAMEWORK config exists in this project; auth/permissions are
applied per-view (house pattern). Rate limits blunt access-code brute force.
"""
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from broadcast.adapters import enabled_adapters, get_adapter, registry
from broadcast.autofill import extract_event_fields
from broadcast.models import BroadcastSubmission
from broadcast.permissions import HasBroadcastAccessCode
from broadcast.routing import eligible_targets
from broadcast.serializers import CanonicalEventSerializer
from broadcast.services import (
    cancel_submission,
    create_submission,
    job_payload,
    manual_recipe,
    retry_targets,
    submit_real_targets,
)


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([HasBroadcastAccessCode])
def preview(request):
    serializer = CanonicalEventSerializer(data=request.data.get("event", {}))
    if not serializer.is_valid():
        return Response({"event": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    ev = serializer.to_canonical()
    eligible, excluded = eligible_targets(ev, enabled_adapters())
    return Response({
        "eligible": [{"site_key": a.key, "name": a.name} for a in eligible],
        "excluded": [{"site_key": k, "reason": r} for k, r in excluded],
    })


@ratelimit(key="ip", rate="3/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([HasBroadcastAccessCode])
def submit(request):
    serializer = CanonicalEventSerializer(data=request.data.get("event", {}))
    if not serializer.is_valid():
        return Response({"event": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response({"site_keys": "select at least one site"},
                        status=status.HTTP_400_BAD_REQUEST)
    unknown = [k for k in site_keys if k not in registry()]
    if unknown:
        return Response({"site_keys": f"unknown sites: {unknown}"},
                        status=status.HTTP_400_BAD_REQUEST)

    dry_run = request.data.get("dry_run")
    if dry_run is None:
        dry_run = settings.BROADCAST_DRY_RUN_DEFAULT

    submission = create_submission(
        client_label=request.broadcast_client_label,
        event=serializer.to_canonical(),
        site_keys=site_keys,
        dry_run=bool(dry_run),
    )
    return Response({"job_id": str(submission.id)}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([HasBroadcastAccessCode])
def job_detail(request, job_id):
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404
    return Response(job_payload(submission))


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([HasBroadcastAccessCode])
def job_retry(request, job_id):
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404
    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response({"site_keys": "select at least one site"},
                        status=status.HTTP_400_BAD_REQUEST)
    requeued = retry_targets(submission, site_keys)
    return Response({"job_id": str(submission.id), "requeued": requeued})


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([HasBroadcastAccessCode])
def job_submit_real(request, job_id):
    """Promote dry-run targets to a real submission within an existing job."""
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404
    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response({"site_keys": "select at least one site"},
                        status=status.HTTP_400_BAD_REQUEST)
    submitted = submit_real_targets(submission, site_keys)
    return Response({"job_id": str(submission.id), "submitted": submitted})


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([HasBroadcastAccessCode])
def job_cancel(request, job_id):
    """Stop a job — skip pending targets and mark the submission canceled."""
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404
    skipped = cancel_submission(submission)
    return Response({
        "job_id": str(submission.id),
        "status": submission.status,
        "skipped": skipped,
    })


@api_view(["GET"])
@permission_classes([HasBroadcastAccessCode])
def job_screenshot(request, job_id, site_key):
    """Operator-gated screenshot access — never expose the directory publicly."""
    if get_adapter(site_key) is None:
        raise Http404
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404
    target = submission.targets.filter(site_key=site_key).first()
    if not target or not target.screenshot_path:
        raise Http404
    base = os.path.realpath(settings.BROADCAST_SCREENSHOT_DIR)
    path = os.path.realpath(target.screenshot_path)
    if not path.startswith(base + os.sep) or not os.path.exists(path):
        raise Http404
    return FileResponse(open(path, "rb"), content_type="image/png")


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@api_view(["GET"])
@permission_classes([HasBroadcastAccessCode])
def job_manual_recipe(request, job_id, site_key):
    """Recipe for a needs_manual target — the manual-review extension fills it.

    Access is gated by the same access-code header the SPA already holds, so the
    event data is never exposed beyond what the operator could already see.
    """
    adapter = get_adapter(site_key)
    if adapter is None or not adapter.recipe_fields:
        raise Http404
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404
    target = submission.targets.filter(site_key=site_key).first()
    if not target:
        raise Http404
    if target.status != "needs_manual":
        return Response({"detail": "target is not awaiting manual review"},
                        status=status.HTTP_409_CONFLICT)
    return Response(manual_recipe(submission, site_key))


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([HasBroadcastAccessCode])
def ai_autofill(request):
    """Extract EventDraft fields from free text via Gemini and return them for human review.

    No DB writes, no preview, no submit — pure field extraction only.
    """
    text = request.data.get("text", "")
    if not text or not text.strip():
        return Response({"text": "paste some event text first"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        event = extract_event_fields(text)
    except Exception:
        return Response(
            {"error": "AI autofill is unavailable right now — fill the form manually."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({"event": event})


def mock_form(request):
    """Dev-only: serves the local mock submission form (adapter integration tests)."""
    if not settings.DEBUG:
        raise Http404
    html_path = os.path.join(os.path.dirname(__file__), "adapters", "_mock_form.html")
    with open(html_path) as f:
        return HttpResponse(f.read())
