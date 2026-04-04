from rest_framework import serializers
from .models import Event, Tag, Town

class EventSerializer(serializers.ModelSerializer):
    # Tags: write_only list of strings, read_only tag_names
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True
    )
    tag_names = serializers.StringRelatedField(many=True, source='tags', read_only=True)

    # Town: accepts/returns the slug string (e.g. 'carrboro')
    town = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Town.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Event
        fields = ['uuid', 'title', 'town', 'date', 'venue', 'description', 'price', 'photo', 'link', 'tags', 'tag_names']

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])

        event = Event.objects.create(**validated_data)

        for tag_name in tags_data:
            tag_clean = tag_name.strip().lower()
            tag_obj, _ = Tag.objects.get_or_create(name=tag_clean)
            event.tags.add(tag_obj)

        return event