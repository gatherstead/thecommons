from rest_framework import serializers

from broadcast.routing import CATEGORIES, LOCALITIES
from broadcast.schema import CanonicalEvent, _to_local


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
    organizer_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    contact_email = serializers.EmailField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")

    def to_canonical(self) -> CanonicalEvent:
        data = dict(self.validated_data)
        data["start_datetime"] = _to_local(data["start_datetime"])
        data["end_datetime"] = _to_local(data.get("end_datetime") or None)
        return CanonicalEvent(**data)
