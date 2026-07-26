"""Broadcast API views. Thin — eligibility in routing.py, persistence in services.py.

No global REST_FRAMEWORK config exists in this project; auth/permissions are
applied per-view (house pattern). Rate limits blunt access-code brute force.
"""

import io
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse
from django_ratelimit.decorators import ratelimit
from PIL import Image, UnidentifiedImageError
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from broadcast import cache as broadcast_cache
from broadcast.access import redeem_upgrade_code, resolve_access
from broadcast.adapters import enabled_adapters, get_adapter, registry
from broadcast.autofill import extract_event_fields
from broadcast.models import AccessCodeUse, BroadcastImage, BroadcastSubmission
from broadcast.permissions import (
    RequiresBroadcastLogin,
    RequiresBroadcastTier1,
    RequiresBroadcastTier2,
    _draft_id_from,
)
from broadcast.routing import eligible_targets
from broadcast.serializers import BroadcastImageUploadSerializer, CanonicalEventSerializer
from broadcast.services import (
    cancel_submission,
    create_submission,
    force_retry_stuck_target,
    job_payload,
    manual_recipe,
    retry_targets,
    submit_real_targets,
)

# Re-encoded output caps — the source image is discarded, never stored as
# received. Confirmed limits: 10 MB in (BroadcastImageUploadSerializer), 4000px
# max edge out.
MAX_IMAGE_EDGE_PX = 4000

# Maps AccessResult.reason (set by resolve_access for a matched-but-dead trial
# code) to the message shown to the caller. Falls back to a generic message.
_ACCESS_DENIED_DETAIL = {
    "expired": "This access code has expired — please contact support.",
    "exhausted": "This access code has no uses remaining — please contact support.",
}


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def preview(request):
    serializer = CanonicalEventSerializer(data=request.data.get("event", {}))
    if not serializer.is_valid():
        return Response({"event": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    if request.broadcast_access.is_trial:
        draft_id = _draft_id_from(request)
        if draft_id is None:
            return Response({"draft_id": "required"}, status=status.HTTP_400_BAD_REQUEST)
        AccessCodeUse.objects.get_or_create(
            access_code=request.broadcast_access.code,
            draft_id=draft_id,
        )

    ev = serializer.to_canonical()
    eligible, excluded = eligible_targets(ev, enabled_adapters())
    return Response(
        {
            "eligible": [{"site_key": a.key, "name": a.name} for a in eligible],
            "excluded": [{"site_key": k, "reason": r} for k, r in excluded],
        }
    )


@ratelimit(key="ip", rate="3/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def submit(request):
    serializer = CanonicalEventSerializer(data=request.data.get("event", {}))
    if not serializer.is_valid():
        return Response({"event": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response(
            {"site_keys": "select at least one site"}, status=status.HTTP_400_BAD_REQUEST
        )
    unknown = [k for k in site_keys if k not in registry()]
    if unknown:
        return Response(
            {"site_keys": f"unknown sites: {unknown}"}, status=status.HTTP_400_BAD_REQUEST
        )

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
@permission_classes([RequiresBroadcastTier1])
def job_detail(request, job_id):
    """Poll target — broadcastWeb hits this every 3s while a job runs, so a
    cache hit must never touch Neon. Miss path (cold cache) falls back to the
    DB and repopulates the cache for subsequent polls."""
    cached = broadcast_cache.get_job_payload(job_id)
    if cached is not None:
        return Response(cached)

    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404 from None
    payload = job_payload(submission)
    broadcast_cache.set_job_payload(job_id, payload)
    return Response(payload)


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def job_retry(request, job_id):
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404 from None
    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response(
            {"site_keys": "select at least one site"}, status=status.HTTP_400_BAD_REQUEST
        )
    requeued = retry_targets(submission, site_keys)
    return Response({"job_id": str(submission.id), "requeued": requeued})


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def job_retry_stuck(request, job_id):
    """Recover targets frozen in_progress by a worker that died mid-run."""
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404 from None
    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response(
            {"site_keys": "select at least one site"}, status=status.HTTP_400_BAD_REQUEST
        )
    requeued = force_retry_stuck_target(submission, site_keys)
    return Response({"job_id": str(submission.id), "requeued": requeued})


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def job_submit_real(request, job_id):
    """Promote dry-run targets to a real submission within an existing job."""
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404 from None
    site_keys = request.data.get("site_keys") or []
    if not isinstance(site_keys, list) or not site_keys:
        return Response(
            {"site_keys": "select at least one site"}, status=status.HTTP_400_BAD_REQUEST
        )
    submitted = submit_real_targets(submission, site_keys)
    return Response({"job_id": str(submission.id), "submitted": submitted})


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def job_cancel(request, job_id):
    """Stop a job — skip pending targets and mark the submission canceled."""
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404 from None
    skipped = cancel_submission(submission)
    return Response(
        {
            "job_id": str(submission.id),
            "status": submission.status,
            "skipped": skipped,
        }
    )


@api_view(["GET"])
@permission_classes([RequiresBroadcastTier1])
def job_screenshot(request, job_id, site_key):
    """Operator-gated screenshot access — never expose the directory publicly."""
    if get_adapter(site_key) is None:
        raise Http404
    try:
        submission = BroadcastSubmission.objects.get(id=job_id)
    except BroadcastSubmission.DoesNotExist:
        raise Http404 from None
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
@permission_classes([RequiresBroadcastTier1])
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
        raise Http404 from None
    target = submission.targets.filter(site_key=site_key).first()
    if not target:
        raise Http404
    if target.status != "needs_manual":
        return Response(
            {"detail": "target is not awaiting manual review"}, status=status.HTTP_409_CONFLICT
        )
    return Response(manual_recipe(submission, site_key))


@ratelimit(key="ip", rate="30/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier1])
def direct_recipe(request):
    """Return a fill recipe for a site directly from event data — no job required.

    Backs the extension-autofill-first flow where the SPA sends a recipe to the
    extension for every selected site without creating a BroadcastSubmission.
    """
    site_key = request.data.get("site_key", "")
    adapter = get_adapter(site_key)
    if adapter is None or not adapter.recipe_fields:
        raise Http404

    serializer = CanonicalEventSerializer(data=request.data.get("event", {}))
    if not serializer.is_valid():
        return Response({"event": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    return Response(adapter.recipe(serializer.to_canonical()))


@ratelimit(key="ip", rate="30/m", method="POST", block=True)
@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([RequiresBroadcastTier1])
def upload_image(request):
    """Self-host a client-uploaded event image so the extension can fetch it
    reliably (third-party share links are often not direct image URLs and most
    hosts send no CORS headers — see docs/broadcast.md). The upload is
    re-encoded via Pillow rather than stored as received, and EXIF is dropped.
    """
    serializer = BroadcastImageUploadSerializer(data=request.data)
    if not serializer.is_valid():
        detail = next(iter(serializer.errors.get("image", [])), None) or "Invalid upload."
        return Response({"detail": str(detail)}, status=status.HTTP_400_BAD_REQUEST)

    upload = serializer.validated_data["image"]
    try:
        img = Image.open(upload)
        img.verify()
    except (UnidentifiedImageError, OSError):
        return Response(
            {"detail": "That file doesn't look like a valid image — please try a JPEG or PNG."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # verify() leaves the file unusable for further ops — reopen it.
    upload.seek(0)
    try:
        img = Image.open(upload)
        img.load()
    except (UnidentifiedImageError, OSError):
        return Response(
            {"detail": "That file doesn't look like a valid image — please try a JPEG or PNG."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        img = img.convert("RGBA")
        out_format, ext = "PNG", "png"
    else:
        img = img.convert("RGB")
        out_format, ext = "JPEG", "jpg"

    if img.width > MAX_IMAGE_EDGE_PX or img.height > MAX_IMAGE_EDGE_PX:
        return Response(
            {
                "detail": (
                    "That image is too large "
                    f"({img.width}x{img.height}px) — please upload one no larger "
                    f"than {MAX_IMAGE_EDGE_PX}px on a side."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    buffer = io.BytesIO()
    save_kwargs = {"quality": 90, "optimize": True} if out_format == "JPEG" else {"optimize": True}
    img.save(buffer, format=out_format, **save_kwargs)

    record = BroadcastImage.objects.create(client_label=request.broadcast_client_label)
    record.image.save(f"{record.id}.{ext}", ContentFile(buffer.getvalue()), save=True)

    return Response(
        {"url": request.build_absolute_uri(record.image.url)}, status=status.HTTP_201_CREATED
    )


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastTier2])
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


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@api_view(["GET"])
def access_info(request):
    """Return the caller's current access tier and trial metadata.

    No permission class — open to all. Returns 403 only when credentials
    were supplied but could not be validated (invalid JWT or unknown code).
    A matched-but-dead trial code gets a specific message via result.reason.
    """
    result = resolve_access(request)

    auth_header = request.headers.get("Authorization", "")
    code_header = request.headers.get("X-Broadcast-Access-Code", "")
    credentials_supplied = auth_header.startswith("Bearer ") or bool(code_header)

    if credentials_supplied and result.identity is None:
        detail = _ACCESS_DENIED_DETAIL.get(result.reason, "Invalid credentials.")
        return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)

    return Response(
        {
            "tier": result.tier,
            "is_trial": result.is_trial,
            "uses_remaining": result.uses_remaining,
        }
    )


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@api_view(["POST"])
@permission_classes([RequiresBroadcastLogin])
def redeem(request):
    """Redeem an UPGRADE access code, permanently setting the caller's tier.

    Requires login (JWT) — TRIAL codes are not accepted here, and this never
    grants a per-request tier the way the anonymous code path does.
    """
    raw_code = request.data.get("access_code") if isinstance(request.data, dict) else None
    if not raw_code or not isinstance(raw_code, str):
        return Response({"access_code": "required"}, status=status.HTTP_400_BAD_REQUEST)

    new_tier = redeem_upgrade_code(request.broadcast_email, raw_code)
    if new_tier is None:
        return Response(
            {"detail": "Access code not recognized, expired, or already used up."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return Response({"tier": new_tier})


def mock_form(request):
    """Dev-only: serves the local mock submission form (adapter integration tests)."""
    if not settings.DEBUG:
        raise Http404
    html_path = os.path.join(os.path.dirname(__file__), "adapters", "_mock_form.html")
    with open(html_path) as f:
        return HttpResponse(f.read())
