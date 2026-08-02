import uuid

from django.db import models


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Town(models.Model):
    slug = models.CharField(max_length=100, unique=True)  # e.g. 'carrboro'
    name = models.CharField(max_length=100)  # e.g. 'Carrboro'

    def __str__(self):
        return self.name


class Category(models.Model):
    slug = models.SlugField(unique=True)
    display_name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.display_name


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=200)

    town = models.ForeignKey(
        "Town", null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )

    date = models.DateTimeField(db_index=True)

    venue = models.CharField(max_length=200)

    description = models.TextField()

    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    photo = models.ImageField(upload_to="event_photos/", null=True, blank=True)

    tags = models.ManyToManyField(Tag, related_name="events", blank=True)

    categories = models.ManyToManyField(Category, related_name="events", blank=True)

    link = models.URLField(max_length=500, blank=True)

    is_verified = models.BooleanField(default=False)
    source_name = models.CharField(max_length=200, blank=True, default="")

    # Tracks who submitted this event; null for pipeline-ingested events.
    created_by = models.ForeignKey(
        "accounts.BetterAuthUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_events",
        db_constraint=False,
    )

    def __str__(self):
        return self.title
