from rest_framework import serializers
from .models import Event, Tag, Town, Category, BusinessProfile

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

    # Categories: write_only list of slugs, read_only category_slugs
    categories = serializers.ListField(
        child=serializers.CharField(max_length=100),
        write_only=True,
        required=False,
    )
    category_slugs = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        source='categories',
        slug_field='slug',
    )

    class Meta:
        model = Event
        fields = ['uuid', 'title', 'town', 'date', 'venue', 'description', 'price', 'photo', 'link', 'tags', 'tag_names', 'categories', 'category_slugs', 'is_verified', 'source_name']

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])
        categories_data = validated_data.pop('categories', [])

        event = Event.objects.create(**validated_data)

        for tag_name in tags_data:
            tag_clean = tag_name.strip().lower()
            tag_obj, _ = Tag.objects.get_or_create(name=tag_clean)
            event.tags.add(tag_obj)

        for slug in categories_data:
            try:
                cat = Category.objects.get(slug=slug.strip())
                event.categories.add(cat)
            except Category.DoesNotExist:
                pass

        return event


class BusinessProfileSerializer(serializers.ModelSerializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True,
        required=False,
    )
    tag_names = serializers.StringRelatedField(many=True, source='tags', read_only=True)

    service_area = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Town.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = BusinessProfile
        fields = [
            'uuid', 'business_name', 'description', 'tags', 'tag_names',
            'service_area', 'contact_email', 'contact_phone', 'is_published',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['uuid', 'created_at', 'updated_at']

    def _resolve_tags(self, tag_names):
        tag_objs = []
        for name in tag_names:
            clean = name.strip().lower()
            if not clean:
                continue
            tag_obj, _ = Tag.objects.get_or_create(name=clean)
            tag_objs.append(tag_obj)
        return tag_objs

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])
        service_area_data = validated_data.pop('service_area', [])

        business = BusinessProfile.objects.create(**validated_data)
        business.tags.set(self._resolve_tags(tags_data))
        business.service_area.set(service_area_data)
        return business

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        service_area_data = validated_data.pop('service_area', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tags_data is not None:
            instance.tags.set(self._resolve_tags(tags_data))
        if service_area_data is not None:
            instance.service_area.set(service_area_data)
        return instance