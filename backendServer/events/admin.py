from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Tag, Town, UserProfile, Event


@admin.register(Tag)
class TagAdmin(ModelAdmin):
    pass


@admin.register(Town)
class TownAdmin(ModelAdmin):
    list_display = ['name', 'slug']


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    pass


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ['title', 'town', 'venue', 'date']
    list_filter = ['town']
    search_fields = ['title', 'description', 'venue']
