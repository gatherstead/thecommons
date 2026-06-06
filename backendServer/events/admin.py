from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Tag, Town, UserProfile, Event, NewsletterSubscriber, BusinessProfile


@admin.register(Tag)
class TagAdmin(ModelAdmin):
    pass


@admin.register(Town)
class TownAdmin(ModelAdmin):
    list_display = ['name', 'slug']


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    # `user` points to a managed=False model in neon_auth — no FK constraint
    # and no <select> widget makes sense; show a raw id lookup instead.
    raw_id_fields = ('user',)
    list_display = ['user', 'user_type', 'primary_city']


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(ModelAdmin):
    list_display = ['email', 'frequency', 'is_active', 'subscribed_at']
    list_filter = ['frequency', 'is_active']
    search_fields = ['email']


@admin.register(BusinessProfile)
class BusinessProfileAdmin(ModelAdmin):
    # `user` points to a managed=False model in neon_auth — show a raw id lookup.
    raw_id_fields = ('user',)
    list_display = ['business_name', 'user', 'is_published', 'created_at']
    list_filter = ['is_published']
    search_fields = ['business_name', 'description']


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ['title', 'town', 'venue', 'date']
    list_filter = ['town']
    search_fields = ['title', 'description', 'venue']
