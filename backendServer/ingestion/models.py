from django.db import models


class EventSource(models.Model):
    """A URL we poll on a schedule to discover events."""

    SOURCE_TYPES = [
        ("ics", "ICS/iCal Feed"),
        ("scraper", "Web Scraper"),
        ("http", "HTTP Fetch"),
        ("email", "Email Inbox"),
        ("direct", "Direct Host Submission"),
    ]

    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    url = models.URLField(max_length=500)
    active = models.BooleanField(default=True)
    last_polled = models.DateTimeField(null=True, blank=True)
    poll_interval_hours = models.IntegerField(default=24)
    notes = models.TextField(blank=True)
    prompt_suffix = models.TextField(blank=True, default="")
    scraper_key = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.source_type})"


class SourceRun(models.Model):
    """One row per per-source poll attempt, recorded for observability."""

    STATUS_CHOICES = [
        ("ok", "Ok"),
        ("failed", "Failed"),
        ("refused", "Refused"),
        ("skipped", "Skipped"),
    ]

    TRIGGER_CHOICES = [
        ("scheduled", "Scheduled"),
        ("probe", "Probe"),
        ("manual", "Manual"),
    ]

    source = models.ForeignKey(EventSource, on_delete=models.CASCADE, related_name="runs")

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default="scheduled")

    items_fetched = models.IntegerField(default=0)
    items_new = models.IntegerField(default=0)
    items_duplicate = models.IntegerField(default=0)

    error_class = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["source", "-started_at"])]
        ordering = ["-started_at"]

    def __str__(self):
        return f"[{self.status}] run {self.pk} for source_id={self.source_id}"


class RawEvent(models.Model):
    """Events as scraped, before LLM processing."""

    source = models.ForeignKey(EventSource, on_delete=models.CASCADE, related_name="raw_events")

    raw_title = models.CharField(max_length=500)
    raw_description = models.TextField(blank=True)
    raw_location = models.CharField(max_length=500, blank=True)
    raw_start = models.DateTimeField()
    raw_end = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    source_uid = models.CharField(max_length=500, blank=True)

    # Organizer name as submitted (direct host submissions only); drives the
    # "Direct submission by {name}" attribution on the published Event.
    raw_organizer = models.CharField(max_length=200, blank=True)

    processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["source", "source_uid"]

    def __str__(self):
        return f"[Raw] {self.raw_title} ({self.source.name})"


class StagedEvent(models.Model):
    """Events after LLM standardization, waiting for admin review."""

    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("duplicate", "Duplicate"),
        ("published", "Published"),
        ("skipped_no_town", "Skipped — No Matching Town"),
    ]

    raw_event = models.OneToOneField(
        RawEvent,
        on_delete=models.CASCADE,
        related_name="staged",
        null=True,
        blank=True,
    )

    # LLM-standardized fields
    title = models.CharField(max_length=500)
    description = models.TextField()
    location_name = models.CharField(max_length=255)
    town = models.CharField(max_length=100)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list)
    category = models.CharField(max_length=100, blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    link = models.URLField(max_length=500, blank=True)

    # Review workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reviewer_notes = models.TextField(blank=True)
    duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicates",
    )

    # Safety scoring
    safety_score = models.FloatField(null=True, blank=True)
    safety_notes = models.TextField(blank=True, default="")

    # Link to the real Event once approved
    published_event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staged_source",
    )

    # Tracks who submitted this event via the public API; null for pipeline events.
    submitted_by = models.ForeignKey(
        "accounts.BetterAuthUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_staged_events",
        db_constraint=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.status}] {self.title}"
