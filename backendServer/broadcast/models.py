from uuid import uuid4

from django.db import models


class BroadcastSubmission(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    client_label = models.CharField(max_length=64)
    title = models.CharField(max_length=300)
    description = models.TextField()
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    venue_name = models.CharField(max_length=200)
    address_line1 = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=2, default="NC")
    zip = models.CharField(max_length=10)
    locality = models.JSONField(default=list)
    categories = models.JSONField(default=list)
    event_url = models.URLField(max_length=500, blank=True)
    ticket_url = models.URLField(max_length=500, blank=True)
    price = models.CharField(max_length=60, blank=True)
    is_free = models.BooleanField(default=False)
    image_url = models.URLField(max_length=500, blank=True)
    organizer_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, default="queued", choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.client_label}, {self.status})"


class BroadcastTarget(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In progress"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("needs_manual", "Needs manual"),
        ("skipped", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    submission = models.ForeignKey(
        BroadcastSubmission, related_name="targets", on_delete=models.CASCADE
    )
    site_key = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="pending", choices=STATUS_CHOICES)
    attempts = models.PositiveSmallIntegerField(default=0)
    external_url = models.URLField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    screenshot_path = models.CharField(max_length=300, blank=True)
    dry_run = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "site_key"], name="uniq_submission_site"
            )
        ]

    def __str__(self):
        return f"{self.site_key}: {self.status}"
