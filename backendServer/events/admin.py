from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Event, Tag, Town


@admin.register(Tag)
class TagAdmin(ModelAdmin):
    pass


@admin.register(Town)
class TownAdmin(ModelAdmin):
    list_display = ["name", "slug"]


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ["title", "town", "venue", "date"]
    list_filter = ["town"]
    search_fields = ["title", "description", "venue"]
