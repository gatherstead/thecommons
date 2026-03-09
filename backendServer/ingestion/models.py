from django.db import models


class EventSource(models.Model):
    """A URL we poll on a schedule to discover events."""

    SOURCE_TYPES = [
        ('ics', 'ICS/iCal Feed'),
        ('scraper', 'Web Scraper'),
        ('email', 'Email Inbox'),
    ]

    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    url = models.URLField(max_length=500)
    active = models.BooleanField(default=True)
    last_polled = models.DateTimeField(null=True, blank=True)
    poll_interval_hours = models.IntegerField(default=24)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.source_type})"


class RawEvent(models.Model):
    """Events as scraped, before LLM processing."""

    source = models.ForeignKey(
        EventSource, on_delete=models.CASCADE, related_name='raw_events'
    )

    raw_title = models.CharField(max_length=500)
    raw_description = models.TextField(blank=True)
    raw_location = models.CharField(max_length=500, blank=True)
    raw_start = models.DateTimeField()
    raw_end = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    source_uid = models.CharField(max_length=500, blank=True)

    processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['source', 'source_uid']

    def __str__(self):
        return f"[Raw] {self.raw_title} ({self.source.name})"


class StagedEvent(models.Model):
    """Events after LLM standardization, waiting for admin review."""

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('duplicate', 'Duplicate'),
    ]

    raw_event = models.OneToOneField(
        RawEvent, on_delete=models.CASCADE, related_name='staged'
    )

    # LLM-standardized fields
    title = models.CharField(max_length=500)
    description = models.TextField()
    location_name = models.CharField(max_length=255)
    town = models.CharField(max_length=100)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list)

    # Review workflow
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    reviewer_notes = models.TextField(blank=True)
    duplicate_of = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='duplicates',
    )

    # Link to the real Event once approved
    published_event = models.ForeignKey(
        'events.Event', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='staged_source',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.status}] {self.title}"
