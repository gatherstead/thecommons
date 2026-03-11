from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Tag, UserProfile, Event


@admin.register(Tag)
class TagAdmin(ModelAdmin):
    pass


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    pass


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ['title', 'town', 'venue', 'date']
    list_filter = ['town']
    search_fields = ['title', 'description', 'venue']
