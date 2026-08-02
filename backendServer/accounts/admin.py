from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import BusinessProfile, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    # `user` points to a managed=False model in neon_auth — no FK constraint
    # and no <select> widget makes sense; show a raw id lookup instead.
    # list_display uses user_id (a plain column) rather than user (the FK
    # object) so the changelist doesn't issue a per-row query against
    # neon_auth.user, which doesn't exist on Postgres instances outside Neon.
    raw_id_fields = ("user",)
    list_display = ["user_id", "user_type", "primary_city"]


@admin.register(BusinessProfile)
class BusinessProfileAdmin(ModelAdmin):
    # `user` points to a managed=False model in neon_auth — show a raw id lookup.
    # list_display uses user_id rather than user (see UserProfileAdmin above).
    raw_id_fields = ("user",)
    list_display = ["business_name", "user_id", "is_published", "created_at"]
    list_filter = ["is_published"]
    search_fields = ["business_name", "description"]
