import uuid

from django.db import models


class NewsletterSubscriber(models.Model):
    class Frequency(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"

    email = models.EmailField(unique=True)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.WEEKLY)
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    manage_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        db_table = "events_newslettersubscriber"

    def __str__(self):
        return f"{self.email} ({self.frequency})"
