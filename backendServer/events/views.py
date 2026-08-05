from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import UserProfile
from backend.permissions import BearerTokenAuthentication, HasCommonsAPIKeyOrUser
from ingestion.models import StagedEvent

from . import cache as events_cache
from .models import Event, Town
from .serializers import EventSerializer

PAGE_SIZE = 30


class EventsPagination(PageNumberPagination):
    page_size = PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = 100


@api_view(["GET"])
def get_towns(request):
    data = cache.get(events_cache.TOWNS_CACHE_KEY)
    if data is None:
        towns = Town.objects.all().order_by("name")
        data = [{"slug": t.slug, "name": t.name} for t in towns]
        cache.set(events_cache.TOWNS_CACHE_KEY, data, events_cache.STATIC_TTL)
    return Response(data)


def _filtered_events_queryset(request):  # noqa: C901  # query-param filtering; complexity is inherent
    """
    Shared window/date filtering for the events list and facet-count endpoints.

    Query params (applied in priority order — after/before/include_past override window):
      after        ISO datetime — events on or after this datetime
      before       ISO datetime — events on or before this datetime
      include_past bool        — include all past events (no lower bound)
      window       default | past | future
                   default: now <= date <= now + 90 days if ≥30 events exist there,
                            otherwise date >= now (fills page from all future events)
                   past:    date < now
                   future:  date > now + 90 days
      tag          repeatable (?tag=a&tag=b) — AND within the group: an event must
                   carry every requested tag, not just one of them
      town         repeatable (?town=a&town=b) — OR within the group

    Note: does NOT apply `.order_by()` — callers that care about ordering (e.g. get_all's
    "past" window, which reverses to newest-first) must apply it themselves.
    """
    now = timezone.now()
    ninety_days_out = now + timedelta(days=90)

    events = Event.objects.all()

    include_past = request.query_params.get("include_past", "").lower() == "true"
    after_param = request.query_params.get("after")
    before_param = request.query_params.get("before")
    window = request.query_params.get("window", "").lower()
    is_past_window = False  # only set by the unqualified window=past branch below

    # after/before/include_past are explicit overrides; window applies only when none are set
    if after_param or before_param or include_past:
        if after_param:
            after_dt = parse_datetime(after_param)
            if after_dt:
                events = events.filter(date__gte=after_dt)
        elif not include_past:
            events = events.filter(date__gte=now)

        if before_param:
            before_dt = parse_datetime(before_param)
            if before_dt:
                events = events.filter(date__lte=before_dt)
    else:
        if window == "past":
            events = events.filter(date__lt=now)
            is_past_window = True
        elif window == "future":
            events = events.filter(date__gt=ninety_days_out)
        else:  # 'default' or unset — 90-day cap unless fewer than PAGE_SIZE events exist there
            qs_90 = events.filter(date__gte=now, date__lte=ninety_days_out)
            if qs_90.count() >= PAGE_SIZE:
                events = qs_90
            else:
                events = events.filter(date__gte=now)

    # Multi-tag is AND (an event must carry every selected tag), unlike town
    # which is OR within its own group. A single `tags__name__in=[...]` filter would
    # give OR semantics, so each tag gets its own chained `.filter()` call — each one
    # adds its own join, which is what makes the AND work.
    #
    # Known mismatch (accepted, not a bug): the sidebar's per-tag facet counts are
    # computed independently per tag, so a 2-tag AND selection can legitimately return
    # fewer events than either individual facet count suggests.
    tag_param = request.query_params.getlist("tag")
    for tag_name in tag_param:
        events = events.filter(tags__name=tag_name)
    if tag_param:
        events = events.distinct()

    town_param = request.query_params.getlist("town")
    if town_param:
        events = events.filter(town__slug__in=town_param)

    return events, is_past_window


@api_view(["GET"])
def get_all(request):
    """
    List published events (paginated, page_size=30).

    See `_filtered_events_queryset` for the supported query params.
    """
    cache_key = events_cache.events_list_key(request.query_params)
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    events, is_past_window = _filtered_events_queryset(request)
    events = events.order_by("-date") if is_past_window else events.order_by("date")

    paginator = EventsPagination()
    page = paginator.paginate_queryset(events, request)
    serializer = EventSerializer(page, many=True)
    data = paginator.get_paginated_response(serializer.data).data
    cache.set(cache_key, data, events_cache.EVENTS_LIST_TTL)
    return Response(data)


@api_view(["GET"])
def get_facets(request):
    """
    Facet counts (towns, tags) over the full filtered event set — unpaginated.

    Accepts the same window/date query params as `get_all`. Used by the
    frontend sidebar so counts reflect the whole filtered result, not just the
    current page.
    """
    cache_key = events_cache.events_facets_key(request.query_params)
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    events, _is_past_window = _filtered_events_queryset(request)

    town_counts = (
        events.exclude(town__isnull=True)
        .values("town__slug")
        .annotate(n=Count("pk", distinct=True))
    )
    tag_counts = (
        events.exclude(tags__isnull=True)
        .values("tags__name")
        .annotate(n=Count("pk", distinct=True))
    )

    data = {
        "towns": {row["town__slug"]: row["n"] for row in town_counts if row["town__slug"]},
        "tags": {row["tags__name"]: row["n"] for row in tag_counts if row["tags__name"]},
    }
    cache.set(cache_key, data, events_cache.EVENTS_LIST_TTL)
    return Response(data)


@api_view(["GET", "DELETE"])
@authentication_classes([BearerTokenAuthentication])
def get_one(request, event_id):
    event = get_object_or_404(Event, uuid=event_id)
    if request.method == "DELETE":
        if not getattr(request.user, "is_authenticated", False):
            return Response(
                {"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED
            )
        if event.created_by_id != request.user.id:
            return Response(
                {"error": "You can only delete your own events."}, status=status.HTTP_403_FORBIDDEN
            )
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = EventSerializer(event)
    return Response(serializer.data)


def _coerce_price(value):
    """Normalize a submitted price, keeping 0 (free) distinct from "no price given".

    A plain `value or None` collapses 0 to NULL, which loses the difference between a
    deliberately free event and one whose price was never entered.
    """
    if value is None or value == "":
        return None
    return value


@api_view(["GET", "PATCH", "DELETE"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def manage_staged_event(request, event_id):  # noqa: C901  # multi-method CRUD view; complexity is inherent
    staged = get_object_or_404(StagedEvent, id=event_id, submitted_by=request.user)

    if request.method == "DELETE":
        staged.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if request.method == "GET":
        return Response(
            {
                "id": staged.id,
                "title": staged.title,
                "venue": staged.location_name,
                "town": staged.town,
                "date": staged.start_datetime.isoformat() if staged.start_datetime else None,
                "description": staged.description,
                "price": str(staged.price) if staged.price is not None else "",
                "link": staged.link,
                "tags": staged.tags,
                "status": staged.status,
            }
        )

    # PATCH
    data = request.data
    if "title" in data:
        staged.title = data["title"]
    if "venue" in data:
        staged.location_name = data["venue"]
    if "town" in data:
        staged.town = data["town"]
    if "date" in data:
        dt = parse_datetime(data["date"])
        if dt:
            staged.start_datetime = dt
    if "description" in data:
        staged.description = data["description"]
    if "price" in data:
        staged.price = _coerce_price(data["price"])
    if "link" in data:
        staged.link = data["link"]
    if "tags" in data:
        staged.tags = data["tags"]
    staged.save()
    return Response({"id": staged.id, "status": staged.status})


@api_view(["POST"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([HasCommonsAPIKeyOrUser])
def create_event(request):
    data = request.data

    required = ["title", "town", "venue", "date", "description"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return Response(
            {"error": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST
        )

    submitted_by = request.user if getattr(request.user, "is_authenticated", False) else None

    staged = StagedEvent.objects.create(
        title=data["title"],
        town=data["town"],
        location_name=data["venue"],
        start_datetime=data["date"],
        description=data["description"],
        price=_coerce_price(data.get("price")),
        link=data.get("link", ""),
        tags=data.get("tags", []),
        status="pending",
        submitted_by=submitted_by,
    )

    return Response({"id": staged.id, "status": staged.status}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_my_events(request):
    user = request.user

    staged_qs = StagedEvent.objects.filter(submitted_by=user).order_by("-created_at")
    published_qs = Event.objects.filter(created_by=user).order_by("-date")

    results = []

    for s in staged_qs:
        results.append(
            {
                "id": str(s.id),
                "title": s.title,
                "date": s.start_datetime.isoformat() if s.start_datetime else None,
                "venue": s.location_name,
                "status": s.status,
            }
        )

    for e in published_qs:
        results.append(
            {
                "id": str(e.uuid),
                "title": e.title,
                "date": e.date.isoformat() if e.date else None,
                "venue": e.venue,
                "status": "published",
            }
        )

    results.sort(key=lambda x: x["date"] or "", reverse=True)

    return Response(results)


@api_view(["GET"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_my_profile(request):
    profile = UserProfile.objects.filter(user_id=request.user.id).select_related("user").first()
    if profile is None:
        return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "id": profile.user.id,
            "email": profile.user.email,
            "business_name": profile.user.name,
            "user_type": profile.user_type,
            "primary_city": profile.primary_city,
            "address": profile.address,
            "email_preference": profile.email_preference,
        }
    )
