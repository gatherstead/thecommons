from rest_framework import serializers
from .models import Event, Tag

class EventSerializer(serializers.ModelSerializer):
    # We still need this helper for Tags so you can send ["music", "food"]
    # instead of needing to know the internal ID of every tag.
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True
    )
    
    # This is just for reading (GET requests) so you see names, not IDs
    tag_names = serializers.StringRelatedField(many=True, source='tags', read_only=True)

    class Meta:
        model = Event
        fields = ['uuid', 'title', 'town', 'date', 'venue', 'description', 'price', 'photo', 'tags', 'tag_names']

    def create(self, validated_data):
        # 1. Pop the tags list out (Django can't save this list directly to the Event table)
        tags_data = validated_data.pop('tags', [])
        
        # 2. Create the Event (Price is handled automatically now!)
        event = Event.objects.create(**validated_data)

        # 3. Create or Get the tags and link them
        for tag_name in tags_data:
            tag_clean = tag_name.strip().lower()
            tag_obj, created = Tag.objects.get_or_create(name=tag_clean)
            event.tags.add(tag_obj)

        return event