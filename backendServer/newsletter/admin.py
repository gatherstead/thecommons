from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(ModelAdmin):
    list_display = ["email", "frequency", "is_active", "subscribed_at"]
    list_filter = ["frequency", "is_active"]
    search_fields = ["email"]
