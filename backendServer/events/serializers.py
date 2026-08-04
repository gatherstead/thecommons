from rest_framework import serializers

from .models import Category, Event, Town
from .tagging import apply_tags


class EventSerializer(serializers.ModelSerializer):
    # Tags: write_only list of strings, read_only tag_names
    tags = serializers.ListField(child=serializers.CharField(max_length=50), write_only=True)
    tag_names: serializers.Field = serializers.StringRelatedField(
        many=True, source="tags", read_only=True
    )

    # Town: accepts/returns the slug string (e.g. 'carrboro')
    town = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Town.objects.all(),
        allow_null=True,
        required=False,
    )

    # Categories: write_only list of slugs, read_only category_slugs
    categories = serializers.ListField(
        child=serializers.CharField(max_length=100),
        write_only=True,
        required=False,
    )
    category_slugs: serializers.Field = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        source="categories",
        slug_field="slug",
    )

    class Meta:
        model = Event
        fields = [
            "uuid",
            "title",
            "town",
            "date",
            "venue",
            "description",
            "price",
            "photo",
            "link",
            "tags",
            "tag_names",
            "categories",
            "category_slugs",
            "is_verified",
            "source_name",
        ]

    def create(self, validated_data):
        tags_data = validated_data.pop("tags", [])
        categories_data = validated_data.pop("categories", [])

        event = Event.objects.create(**validated_data)

        apply_tags(event, tags_data)

        for slug in categories_data:
            try:
                cat = Category.objects.get(slug=slug.strip())
                event.categories.add(cat)
            except Category.DoesNotExist:
                pass

        return event
