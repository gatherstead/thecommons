from rest_framework import serializers

from broadcast.routing import CATEGORIES, LOCALITIES
from broadcast.schema import CanonicalEvent, _to_local

MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024
# Hard reject above this many total pixels. This is a memory bound, not a
# quality one: decoding costs ~3 bytes/px and the downscale needs a second
# copy, so 50 MP is ~350 MB transient per concurrent upload on a 6 GB VM whose
# celery services already reserve 5 GB (docker-compose.yml). It also sits under
# Pillow's own decompression-bomb threshold (Image.MAX_IMAGE_PIXELS, ~89 MP),
# so a merely-large real photo gets this message rather than Pillow's generic
# "corrupted image". 50 MP covers any phone or DSLR a client will realistically
# hand us; raise it only alongside a mem_limit on the backend service.
MAX_IMAGE_PIXELS_IN = 50_000_000
# Stored output ceiling on the longest edge. Sources larger than this are
# downscaled by views.upload_image, never rejected.
MAX_IMAGE_EDGE_PX = 8000


class BroadcastImageUploadSerializer(serializers.Serializer):
    """Validates the raw upload before Pillow re-encodes it (views.upload_image).

    Both caps are decided from the file header: DjangoImageField has already run
    Image.open()/verify() by the time validate_image sees the file, so `.image`
    carries the dimensions without a raster ever being allocated. Keep it that
    way — decoding first and measuring after is the DoS vector called out in
    django.forms.ImageField.to_python.
    """

    image = serializers.ImageField(max_length=None, use_url=False)

    def validate_image(self, value):
        if value.size > MAX_IMAGE_UPLOAD_BYTES:
            raise serializers.ValidationError(
                "That photo is too big for our system — please resize it down and try "
                f"again. Files need to be under {MAX_IMAGE_UPLOAD_BYTES // (1024 * 1024)} MB."
            )
        width, height = value.image.size
        if width * height > MAX_IMAGE_PIXELS_IN:
            raise serializers.ValidationError(
                "That photo is too big for our system — please resize it down and try "
                f"again. Around {MAX_IMAGE_EDGE_PX} pixels on the longest side works well."
            )
        return value


class CanonicalEventSerializer(serializers.Serializer):
    """Validates the `event` object of preview/submit requests (§4 schema)."""

    title = serializers.CharField(max_length=300)
    description = serializers.CharField()
    start_datetime = serializers.DateTimeField()
    end_datetime = serializers.DateTimeField(required=False, allow_null=True)
    all_day = serializers.BooleanField(required=False, default=False)
    venue_name = serializers.CharField(max_length=200)
    address_line1 = serializers.CharField(max_length=200)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=2, required=False, default="NC")
    zip = serializers.CharField(max_length=10)
    locality = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(LOCALITIES)),
        allow_empty=False,
    )
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(CATEGORIES)),
        allow_empty=False,
    )
    event_url = serializers.URLField(required=False, allow_blank=True, default="")
    ticket_url = serializers.URLField(required=False, allow_blank=True, default="")
    price = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    is_free = serializers.BooleanField(required=False, default=False)
    image_url = serializers.URLField(required=False, allow_blank=True, default="")
    organizer_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    contact_email = serializers.EmailField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )

    def to_canonical(self) -> CanonicalEvent:
        data = dict(self.validated_data)
        data["start_datetime"] = _to_local(data["start_datetime"])
        data["end_datetime"] = _to_local(data.get("end_datetime") or None)
        return CanonicalEvent(**data)
