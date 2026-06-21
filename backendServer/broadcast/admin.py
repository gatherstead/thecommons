from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from broadcast.models import BroadcastSubmission, BroadcastTarget


class BroadcastTargetInline(TabularInline):
    model = BroadcastTarget
    extra = 0
    fields = ("site_key", "status", "attempts", "dry_run", "external_url", "error", "screenshot_path")
    readonly_fields = fields
    can_delete = False


@admin.register(BroadcastSubmission)
class BroadcastSubmissionAdmin(ModelAdmin):
    list_display = ("title", "client_label", "locality", "status", "created_at", "finished_at")
    list_filter = ("status", "client_label", "locality")
    search_fields = ("title", "venue_name")
    readonly_fields = ("id", "created_at", "started_at", "finished_at")
    inlines = [BroadcastTargetInline]


@admin.register(BroadcastTarget)
class BroadcastTargetAdmin(ModelAdmin):
    list_display = ("site_key", "submission", "status", "attempts", "dry_run", "finished_at")
    list_filter = ("status", "site_key", "dry_run")
    search_fields = ("submission__title", "site_key")
    readonly_fields = ("id", "submission", "started_at", "finished_at")
