from django.contrib import admin
from django.core.management import call_command
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from events.models import Event, Tag
from ingestion.models import EventSource, RawEvent, StagedEvent


@admin.register(EventSource)
class EventSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_type', 'active', 'last_polled', 'event_count']
    list_filter = ['source_type', 'active']
    search_fields = ['name', 'url']
    readonly_fields = ['last_polled', 'created_at', 'updated_at']
    change_list_template = 'ingestion/eventsource_changelist.html'

    def event_count(self, obj):
        return obj.raw_events.count()
    event_count.short_description = '# Events'

    def get_urls(self):
        custom_urls = [
            path(
                'run-ingestion/',
                self.admin_site.admin_view(self.run_ingestion_view),
                name='ingestion_run_pipeline',
            ),
        ]
        return custom_urls + super().get_urls()

    def run_ingestion_view(self, request):
        call_command('ingest_events')
        self.message_user(request, "Ingestion pipeline completed.")
        return HttpResponseRedirect(reverse('admin:ingestion_eventsource_changelist'))


@admin.register(RawEvent)
class RawEventAdmin(admin.ModelAdmin):
    list_display = ['raw_title', 'source', 'raw_start', 'processed', 'created_at']
    list_filter = ['processed', 'source']
    search_fields = ['raw_title', 'raw_description']
    readonly_fields = ['created_at']


@admin.register(StagedEvent)
class StagedEventAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'location_name', 'town', 'start_datetime',
        'status', 'tag_list', 'source_name',
    ]
    list_filter = ['status']
    search_fields = ['title', 'description', 'location_name']
    readonly_fields = ['raw_event', 'created_at', 'updated_at']
    list_editable = ['status']
    actions = ['approve_events', 'reject_events']

    def tag_list(self, obj):
        return ", ".join(obj.tags) if obj.tags else "—"
    tag_list.short_description = 'Tags'

    def source_name(self, obj):
        return obj.raw_event.source.name if obj.raw_event else "—"
    source_name.short_description = 'Source'

    @admin.action(description="Approve selected events")
    def approve_events(self, request, queryset):
        approved = 0
        for staged in queryset.filter(status='pending'):
            # Create the real Event
            event = Event.objects.create(
                title=staged.title,
                town=staged.town,
                date=staged.start_datetime,
                venue=staged.location_name,
                description=staged.description,
            )
            # Add tags
            for tag_name in staged.tags:
                tag_obj, _ = Tag.objects.get_or_create(
                    name=tag_name.strip().lower()
                )
                event.tags.add(tag_obj)

            staged.published_event = event
            staged.status = 'approved'
            staged.save()
            approved += 1
        self.message_user(request, f"Approved {approved} events.")

    @admin.action(description="Reject selected events")
    def reject_events(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='rejected')
        self.message_user(request, f"Rejected {updated} events.")
