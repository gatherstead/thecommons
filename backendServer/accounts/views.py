from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from backend.permissions import BearerTokenAuthentication
from newsletter.models import NewsletterSubscriber

from .models import BusinessProfile, UserProfile
from .serializers import BusinessProfileSerializer


def _account_type(user_id):
    """The authoritative account type lives on UserProfile, not BetterAuthUser."""
    return UserProfile.objects.filter(user_id=user_id).values_list("user_type", flat=True).first()


@api_view(["GET", "POST"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def businesses(request):
    account_type = _account_type(request.user.id)

    if request.method == "GET":
        if account_type != "VENUE":
            return Response(
                {"error": "Only venue accounts can browse the business directory."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = BusinessProfile.objects.filter(is_published=True).prefetch_related(
            "tags", "service_area"
        )

        tag = request.query_params.get("tag")
        if tag:
            qs = qs.filter(tags__name=tag.strip().lower())

        service_area = request.query_params.get("service_area")
        if service_area:
            qs = qs.filter(service_area__slug=service_area.strip())

        q = request.query_params.get("q")
        if q:
            qs = qs.filter(business_name__icontains=q)

        qs = qs.distinct().order_by("business_name")
        return Response(BusinessProfileSerializer(qs, many=True).data)

    # POST
    if account_type != "BUSINESS":
        return Response(
            {"error": "Only business accounts can create a listing."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if BusinessProfile.objects.filter(user_id=request.user.id).exists():
        return Response(
            {"error": "You already have a business listing."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = BusinessProfileSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save(user=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def my_business(request):
    business = (
        BusinessProfile.objects.filter(user_id=request.user.id)
        .prefetch_related("tags", "service_area")
        .first()
    )
    if business is None:
        return Response({"detail": "No business listing."}, status=status.HTTP_404_NOT_FOUND)
    return Response(BusinessProfileSerializer(business).data)


@api_view(["GET", "PATCH", "DELETE"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def business_detail(request, business_id):
    business = get_object_or_404(BusinessProfile, uuid=business_id)
    is_owner = business.user_id == request.user.id

    if request.method == "GET":
        if not is_owner and _account_type(request.user.id) != "VENUE":
            return Response(
                {"error": "You do not have access to this listing."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(BusinessProfileSerializer(business).data)

    if not is_owner:
        return Response(
            {"error": "You can only modify your own listing."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":
        business.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = BusinessProfileSerializer(business, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET", "PATCH"])
@authentication_classes([BearerTokenAuthentication])
@permission_classes([IsAuthenticated])
def me(request):  # noqa: C901  # multi-field profile PATCH; complexity is inherent
    profile = (
        UserProfile.objects.filter(user_id=request.user.id)
        .select_related("user")
        .prefetch_related("tags")
        .first()
    )
    if profile is None:
        return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        data = request.data

        if "email_preference" in data:
            pref = data["email_preference"].upper()
            if pref not in ("WEEKLY", "MONTHLY", "NEVER"):
                return Response(
                    {"error": "email_preference must be WEEKLY, MONTHLY, or NEVER"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.email_preference = pref

        if "user_type" in data:
            new_type = data["user_type"].upper()
            if new_type not in ("BUSINESS", "VENUE"):
                return Response(
                    {"error": "user_type can only be changed to BUSINESS or VENUE"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if profile.user_type == "LOCAL":
                return Response(
                    {"error": "Cannot change account type from LOCAL"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.user_type = new_type

        if "primary_city" in data:
            profile.primary_city = data["primary_city"]

        if "address" in data:
            profile.address = data["address"]

        if "tags" in data:
            from events.models import Tag

            tag_names = [t.strip().lower() for t in data["tags"] if t.strip()]
            tag_objs = []
            for name in tag_names:
                tag_obj, _ = Tag.objects.get_or_create(name=name)
                tag_objs.append(tag_obj)
            profile.tags.set(tag_objs)

        profile.save()

        email = (profile.user.email or "").strip().lower()
        if email:
            if profile.email_preference in ("WEEKLY", "MONTHLY"):
                NewsletterSubscriber.objects.update_or_create(
                    email=email,
                    defaults={"frequency": profile.email_preference, "is_active": True},
                )
            else:
                NewsletterSubscriber.objects.filter(email=email).update(is_active=False)

    return Response(
        {
            "id": profile.user.id,
            "email": profile.user.email,
            "business_name": profile.user.name,
            "user_type": profile.user_type,
            "primary_city": profile.primary_city,
            "address": profile.address,
            "email_preference": profile.email_preference,
            "tags": [t.name for t in profile.tags.all()],
        }
    )
