from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from newsletter.email_service import send_newsletter_welcome

from .models import NewsletterSubscriber


@api_view(["POST"])
def subscribe(request):
    email = request.data.get("email", "").strip().lower()
    frequency = request.data.get("frequency", "WEEKLY").upper()

    if not email:
        return Response({"error": "email is required"}, status=status.HTTP_400_BAD_REQUEST)

    if frequency not in ("WEEKLY", "MONTHLY"):
        return Response(
            {"error": "frequency must be WEEKLY or MONTHLY"}, status=status.HTTP_400_BAD_REQUEST
        )

    subscriber, created = NewsletterSubscriber.objects.update_or_create(
        email=email,
        defaults={"frequency": frequency, "is_active": True},
    )

    send_newsletter_welcome(subscriber.email, subscriber.manage_token)

    return Response(
        {"email": subscriber.email, "frequency": subscriber.frequency},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET", "PATCH"])
def newsletter_manage(request):
    token = request.query_params.get("token")

    subscriber = None
    if token:
        try:
            subscriber = NewsletterSubscriber.objects.filter(manage_token=token).first()
        except ValidationError:
            subscriber = None

    if subscriber is None:
        return Response({"error": "Unknown or invalid token."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        frequency = (request.data.get("frequency") or "").upper()
        if frequency not in ("WEEKLY", "MONTHLY", "NEVER"):
            return Response(
                {"error": "frequency must be WEEKLY, MONTHLY, or NEVER"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if frequency == "NEVER":
            subscriber.is_active = False
        else:
            subscriber.frequency = frequency
            subscriber.is_active = True
        subscriber.save()

    return Response(
        {
            "email": subscriber.email,
            "frequency": subscriber.frequency,
            "is_active": subscriber.is_active,
        }
    )
