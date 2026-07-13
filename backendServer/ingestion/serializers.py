from rest_framework import serializers


class DirectSubmitEventSerializer(serializers.Serializer):
    """Validates the `event` object of direct host submission requests."""

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
    locality = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    categories = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    event_url = serializers.URLField(required=False, allow_blank=True, default="")
    price = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    is_free = serializers.BooleanField(required=False, default=False)
    organizer_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    contact_email = serializers.EmailField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )
